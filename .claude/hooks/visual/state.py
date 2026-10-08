from __future__ import annotations

import sqlite3
import time
import json
from contextlib import closing
from pathlib import Path

from .contracts import ArtifactReceipt, ExplanationPlan, SubagentDigest


def _json_tuple(value: object) -> tuple[str, ...]:
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return ()
    if not isinstance(parsed, (list, tuple)):
        return ()
    return tuple(item for item in parsed if isinstance(item, str))


class StateStore:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=5.0)
        connection.execute("PRAGMA busy_timeout = 5000")
        return connection

    @staticmethod
    def _ensure_column(
        connection: sqlite3.Connection,
        table: str,
        column: str,
        definition: str,
    ) -> None:
        columns = {
            str(row[1])
            for row in connection.execute(f"PRAGMA table_info({table})").fetchall()
        }
        if column not in columns:
            connection.execute(
                f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
            )

    def _initialize(self) -> None:
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS explanation_plans (
                        runtime TEXT NOT NULL,
                        project_hash TEXT NOT NULL,
                        session_id TEXT NOT NULL,
                        turn_id TEXT NOT NULL,
                        response_sha256 TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        expires_at REAL NOT NULL,
                        PRIMARY KEY (
                            runtime,
                            project_hash,
                            session_id,
                            turn_id,
                            response_sha256
                        )
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS preflight_plans (
                        runtime TEXT NOT NULL,
                        project_hash TEXT NOT NULL,
                        session_id TEXT NOT NULL,
                        turn_id TEXT NOT NULL,
                        audience TEXT NOT NULL,
                        depth TEXT NOT NULL,
                        components_json TEXT NOT NULL,
                        reasons_json TEXT NOT NULL,
                        provisional INTEGER NOT NULL,
                        should_continue INTEGER NOT NULL,
                        delivery TEXT NOT NULL,
                        publish_policy TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        expires_at REAL NOT NULL,
                        PRIMARY KEY (runtime, project_hash, session_id, turn_id)
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS artifact_receipts (
                        runtime TEXT NOT NULL,
                        project_hash TEXT NOT NULL,
                        session_id TEXT NOT NULL,
                        turn_id TEXT NOT NULL,
                        project_root TEXT NOT NULL,
                        path TEXT NOT NULL,
                        sha256 TEXT NOT NULL,
                        bytes INTEGER NOT NULL,
                        created_at_text TEXT NOT NULL,
                        gloss_check TEXT NOT NULL,
                        glossary_sha256 TEXT NOT NULL,
                        glossary_source TEXT NOT NULL,
                        visual_smoke TEXT NOT NULL,
                        previewed INTEGER NOT NULL,
                        visibility TEXT NOT NULL,
                        expires_at REAL NOT NULL,
                        PRIMARY KEY (runtime, project_hash, session_id, turn_id)
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS artifact_receipts_v2 (
                        runtime TEXT NOT NULL,
                        project_hash TEXT NOT NULL,
                        session_id TEXT NOT NULL,
                        turn_id TEXT NOT NULL,
                        project_root TEXT NOT NULL,
                        path TEXT NOT NULL,
                        sha256 TEXT NOT NULL,
                        bytes INTEGER NOT NULL,
                        created_at_text TEXT NOT NULL,
                        gloss_check TEXT NOT NULL,
                        glossary_sha256 TEXT NOT NULL,
                        glossary_source TEXT NOT NULL,
                        visual_smoke TEXT NOT NULL,
                        previewed INTEGER NOT NULL,
                        visibility TEXT NOT NULL,
                        expires_at REAL NOT NULL,
                        PRIMARY KEY (runtime, project_hash, session_id, turn_id, path)
                    )
                    """
                )
                self._ensure_column(
                    connection,
                    "preflight_plans",
                    "deprecated_aliases_json",
                    "TEXT NOT NULL DEFAULT '[]'",
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS artifact_receipts_v3 (
                        runtime TEXT NOT NULL,
                        project_hash TEXT NOT NULL,
                        session_id TEXT NOT NULL,
                        turn_id TEXT NOT NULL,
                        project_root TEXT NOT NULL,
                        path TEXT NOT NULL,
                        sha256 TEXT NOT NULL,
                        bytes INTEGER NOT NULL,
                        created_at_text TEXT NOT NULL,
                        gloss_check TEXT NOT NULL,
                        glossary_sha256 TEXT NOT NULL,
                        glossary_source TEXT NOT NULL,
                        visual_smoke TEXT NOT NULL,
                        previewed INTEGER NOT NULL,
                        visibility TEXT NOT NULL,
                        required_components_json TEXT NOT NULL DEFAULT '[]',
                        present_components_json TEXT NOT NULL DEFAULT '[]',
                        missing_components_json TEXT NOT NULL DEFAULT '[]',
                        missing_decision_parts_json TEXT NOT NULL DEFAULT '[]',
                        unwrapped_identifiers_json TEXT NOT NULL DEFAULT '[]',
                        unknown_identifiers_json TEXT NOT NULL DEFAULT '[]',
                        missing_evidence_sources_json TEXT NOT NULL DEFAULT '[]',
                        inspection_errors_json TEXT NOT NULL DEFAULT '[]',
                        inspection_ok INTEGER NOT NULL DEFAULT 1,
                        visual_smoke_errors_json TEXT NOT NULL DEFAULT '[]',
                        expires_at REAL NOT NULL,
                        PRIMARY KEY (runtime, project_hash, session_id, turn_id, path)
                    )
                    """
                )
                connection.execute(
                    """
                    INSERT OR IGNORE INTO artifact_receipts_v3 (
                        runtime, project_hash, session_id, turn_id,
                        project_root, path, sha256, bytes, created_at_text,
                        gloss_check, glossary_sha256, glossary_source,
                        visual_smoke, previewed, visibility,
                        required_components_json, present_components_json,
                        missing_components_json, missing_decision_parts_json,
                        unwrapped_identifiers_json, unknown_identifiers_json,
                        missing_evidence_sources_json, inspection_errors_json,
                        inspection_ok, visual_smoke_errors_json, expires_at
                    )
                    SELECT runtime, project_hash, session_id, turn_id,
                           project_root, path, sha256, bytes, created_at_text,
                           gloss_check, glossary_sha256, glossary_source,
                           visual_smoke, previewed, visibility,
                           '[]', '[]', '[]', '[]', '[]', '[]', '[]', '[]',
                           1, '[]', expires_at
                    FROM artifact_receipts_v2
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS subagent_digests (
                        project_hash TEXT NOT NULL,
                        parent_turn_id TEXT NOT NULL,
                        child_session_id TEXT NOT NULL,
                        goal TEXT NOT NULL,
                        result TEXT NOT NULL,
                        evidence_json TEXT NOT NULL,
                        risk TEXT NOT NULL,
                        needs_human TEXT NOT NULL,
                        status TEXT NOT NULL,
                        duration_ms INTEGER NOT NULL,
                        expires_at REAL NOT NULL,
                        PRIMARY KEY (project_hash, parent_turn_id, child_session_id)
                    )
                    """
                )
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS subagent_digests_v2 (
                        runtime TEXT NOT NULL,
                        profile_id TEXT NOT NULL,
                        session_id TEXT NOT NULL,
                        project_hash TEXT NOT NULL,
                        parent_turn_id TEXT NOT NULL,
                        child_session_id TEXT NOT NULL,
                        goal TEXT NOT NULL,
                        result TEXT NOT NULL,
                        evidence_json TEXT NOT NULL,
                        risk TEXT NOT NULL,
                        needs_human TEXT NOT NULL,
                        status TEXT NOT NULL,
                        duration_ms INTEGER NOT NULL,
                        expires_at REAL NOT NULL,
                        PRIMARY KEY (
                            runtime, profile_id, session_id, project_hash,
                            parent_turn_id, child_session_id
                        )
                    )
                    """
                )
                # 2026-08-29（ユーザー承認＝不具合1）：検品証を**作れなかった**ときの記録。
                # ⚠️今までは作れなかった事実がどこにも残らなかったので、あとから
                #   「何枚見送ったか」を数えられなかった。画面に出すだけだと流れて消えるため、
                #   数えられる場所にも1行残す。id は自動採番＝同じ頁を何度書いても全部残す。
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS receipt_skips (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        runtime TEXT NOT NULL,
                        project_hash TEXT NOT NULL,
                        session_id TEXT NOT NULL,
                        turn_id TEXT NOT NULL,
                        path TEXT NOT NULL,
                        reason TEXT NOT NULL,
                        created_at REAL NOT NULL,
                        expires_at REAL NOT NULL
                    )
                    """
                )
            with connection:
                # ⚠️この表には expires_at を**置かない**＝掃除の対象にしない。
                #   中身（path・理由）は receipt_skips 側で24時間で消えるが、
                #   「その日に何回あったか」だけは永久に残す。
                connection.execute(
                    """
                    CREATE TABLE IF NOT EXISTS receipt_skip_tally (
                        runtime TEXT NOT NULL,
                        project_hash TEXT NOT NULL,
                        day TEXT NOT NULL,
                        count INTEGER NOT NULL,
                        first_seen REAL NOT NULL,
                        last_seen REAL NOT NULL,
                        PRIMARY KEY (runtime, project_hash, day)
                    )
                    """
                )

    def save_receipt_skip(
        self,
        *,
        runtime: str,
        project_hash: str,
        session_id: str,
        turn_id: str,
        path: str,
        reason: str,
        ttl_seconds: int,
        now: float | None = None,
    ) -> None:
        """検品証を作れなかった1件を残す。入れるもの＝対象pathと理由。返るもの＝なし。"""
        current = time.time() if now is None else now
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    "DELETE FROM receipt_skips WHERE expires_at <= ?", (current,)
                )
                connection.execute(
                    """
                    INSERT INTO receipt_skips (
                        runtime, project_hash, session_id, turn_id,
                        path, reason, created_at, expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        runtime,
                        project_hash,
                        session_id,
                        turn_id,
                        path,
                        reason,
                        current,
                        current + ttl_seconds,
                    ),
                )
                # 回数だけを期限なしで足す。⚠️これが無いと、24時間を過ぎた後は
                #   「起きなかった」と「記録が消えた」を区別できなくなる（実害あり）。
                day = time.strftime("%Y-%m-%d", time.gmtime(current))
                connection.execute(
                    """
                    INSERT INTO receipt_skip_tally (
                        runtime, project_hash, day, count, first_seen, last_seen
                    ) VALUES (?, ?, ?, 1, ?, ?)
                    ON CONFLICT(runtime, project_hash, day) DO UPDATE SET
                        count=count + 1,
                        last_seen=excluded.last_seen
                    """,
                    (runtime, project_hash, day, current, current),
                )

    def load_receipt_skips(
        self,
        *,
        project_hash: str,
        session_id: str = "",
        now: float | None = None,
        since: float | None = None,
    ) -> tuple[tuple[str, str], ...]:
        """見送った記録を新しい順に (path, reason) で返す。

        session_id を渡すとそのセッションだけ。since（epoch 秒）を渡すとそれ以後に残した分だけ
        ＝「この回の見送り」を回の開始時刻で切り出すのに使う（2026-10-08）。
        """
        current = time.time() if now is None else now
        query = (
            "SELECT path, reason FROM receipt_skips "
            "WHERE project_hash = ? AND expires_at > ?"
        )
        params: list[object] = [project_hash, current]
        if session_id:
            query += " AND session_id = ?"
            params.append(session_id)
        if since is not None:
            query += " AND created_at >= ?"
            params.append(float(since))
        query += " ORDER BY id DESC"
        with closing(self._connect()) as connection:
            rows = connection.execute(query, params).fetchall()
        return tuple((str(row[0]), str(row[1])) for row in rows)

    def load_receipt_skip_tally(
        self,
        *,
        project_hash: str,
        days: int = 30,
    ) -> tuple[tuple[str, int], ...]:
        """検品証を作れなかった回数を、日ごとに新しい順で返す。

        入れるもの＝プロジェクトの識別子と、遡る日数。返るもの＝`(日付, 回数)` の並び。
        ⚠️中身（どのpathか）はここには無い＝24時間で消える側にある。
          ここに残るのは**回数だけ**なので、後から「その日に何回あったか」は必ず分かる。
        """
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT day, count FROM receipt_skip_tally "
                "WHERE project_hash = ? ORDER BY day DESC LIMIT ?",
                (project_hash, max(1, int(days))),
            ).fetchall()
        return tuple((str(row[0]), int(row[1])) for row in rows)

    def save_digest(
        self,
        *,
        runtime: str,
        profile_id: str,
        session_id: str,
        project_hash: str,
        digest: SubagentDigest,
        ttl_seconds: int,
        now: float | None = None,
    ) -> None:
        current = time.time() if now is None else now
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO subagent_digests_v2 (
                        runtime, profile_id, session_id, project_hash,
                        parent_turn_id, child_session_id,
                        goal, result, evidence_json, risk, needs_human,
                        status, duration_ms, expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(
                        runtime, profile_id, session_id, project_hash,
                        parent_turn_id, child_session_id
                    )
                    DO UPDATE SET
                        goal=excluded.goal,
                        result=excluded.result,
                        evidence_json=excluded.evidence_json,
                        risk=excluded.risk,
                        needs_human=excluded.needs_human,
                        status=excluded.status,
                        duration_ms=excluded.duration_ms,
                        expires_at=excluded.expires_at
                    """,
                    (
                        runtime,
                        profile_id,
                        session_id,
                        project_hash,
                        digest.parent_turn_id,
                        digest.child_session_id,
                        digest.goal,
                        digest.result,
                        json.dumps(digest.evidence, ensure_ascii=False),
                        digest.risk,
                        digest.needs_human,
                        digest.status,
                        digest.duration_ms,
                        current + ttl_seconds,
                    ),
                )

    def load_digests(
        self,
        *,
        runtime: str,
        profile_id: str,
        session_id: str,
        project_hash: str,
        parent_turn_id: str,
        now: float | None = None,
    ) -> tuple[SubagentDigest, ...]:
        current = time.time() if now is None else now
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    "DELETE FROM subagent_digests_v2 WHERE expires_at <= ?",
                    (current,),
                )
                rows = connection.execute(
                    """
                    SELECT child_session_id, goal, result, evidence_json,
                           risk, needs_human, status, duration_ms
                    FROM subagent_digests_v2
                    WHERE runtime=? AND profile_id=? AND session_id=?
                      AND project_hash=? AND parent_turn_id=?
                    ORDER BY child_session_id
                    """,
                    (
                        runtime,
                        profile_id,
                        session_id,
                        project_hash,
                        parent_turn_id,
                    ),
                ).fetchall()
        return tuple(
            SubagentDigest(
                parent_turn_id=parent_turn_id,
                child_session_id=str(row[0]),
                goal=str(row[1]),
                result=str(row[2]),
                evidence=tuple(json.loads(row[3])),
                risk=str(row[4]),
                needs_human=str(row[5]),
                status=str(row[6]),
                duration_ms=int(row[7]),
            )
            for row in rows
        )

    def save_receipt(
        self,
        *,
        project_hash: str,
        receipt: ArtifactReceipt,
        ttl_seconds: int,
        now: float | None = None,
    ) -> None:
        current = time.time() if now is None else now
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO artifact_receipts_v3 (
                        runtime, project_hash, session_id, turn_id,
                        project_root, path, sha256, bytes, created_at_text,
                        gloss_check, glossary_sha256, glossary_source,
                        visual_smoke, previewed, visibility,
                        required_components_json, present_components_json,
                        missing_components_json, missing_decision_parts_json,
                        unwrapped_identifiers_json, unknown_identifiers_json,
                        missing_evidence_sources_json, inspection_errors_json,
                        inspection_ok, visual_smoke_errors_json, expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(runtime, project_hash, session_id, turn_id, path)
                    DO UPDATE SET
                        project_root=excluded.project_root,
                        path=excluded.path,
                        sha256=excluded.sha256,
                        bytes=excluded.bytes,
                        created_at_text=excluded.created_at_text,
                        gloss_check=excluded.gloss_check,
                        glossary_sha256=excluded.glossary_sha256,
                        glossary_source=excluded.glossary_source,
                        visual_smoke=excluded.visual_smoke,
                        previewed=excluded.previewed,
                        visibility=excluded.visibility,
                        required_components_json=excluded.required_components_json,
                        present_components_json=excluded.present_components_json,
                        missing_components_json=excluded.missing_components_json,
                        missing_decision_parts_json=excluded.missing_decision_parts_json,
                        unwrapped_identifiers_json=excluded.unwrapped_identifiers_json,
                        unknown_identifiers_json=excluded.unknown_identifiers_json,
                        missing_evidence_sources_json=excluded.missing_evidence_sources_json,
                        inspection_errors_json=excluded.inspection_errors_json,
                        inspection_ok=excluded.inspection_ok,
                        visual_smoke_errors_json=excluded.visual_smoke_errors_json,
                        expires_at=excluded.expires_at
                    """,
                    (
                        receipt.runtime,
                        project_hash,
                        receipt.session_id,
                        receipt.turn_id,
                        receipt.project_root,
                        receipt.path,
                        receipt.sha256,
                        receipt.bytes,
                        receipt.created_at,
                        receipt.gloss_check,
                        receipt.glossary_sha256,
                        receipt.glossary_source,
                        receipt.visual_smoke,
                        int(receipt.previewed),
                        receipt.visibility,
                        json.dumps(receipt.required_components, ensure_ascii=False),
                        json.dumps(receipt.present_components, ensure_ascii=False),
                        json.dumps(receipt.missing_components, ensure_ascii=False),
                        json.dumps(receipt.missing_decision_parts, ensure_ascii=False),
                        json.dumps(receipt.unwrapped_identifiers, ensure_ascii=False),
                        json.dumps(receipt.unknown_identifiers, ensure_ascii=False),
                        json.dumps(receipt.missing_evidence_sources, ensure_ascii=False),
                        json.dumps(receipt.inspection_errors, ensure_ascii=False),
                        int(receipt.inspection_ok),
                        json.dumps(receipt.visual_smoke_errors, ensure_ascii=False),
                        current + ttl_seconds,
                    ),
                )

    def load_receipt(
        self,
        *,
        runtime: str,
        project_hash: str,
        session_id: str,
        turn_id: str,
        now: float | None = None,
    ) -> ArtifactReceipt | None:
        receipts = self.load_receipts(
            runtime=runtime,
            project_hash=project_hash,
            session_id=session_id,
            turn_id=turn_id,
            now=now,
        )
        return receipts[-1] if receipts else None

    def load_receipts(
        self,
        *,
        runtime: str,
        project_hash: str,
        session_id: str,
        turn_id: str,
        now: float | None = None,
    ) -> tuple[ArtifactReceipt, ...]:
        current = time.time() if now is None else now
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """
                SELECT project_root, path, sha256, bytes, created_at_text,
                       gloss_check, glossary_sha256, glossary_source,
                       visual_smoke, previewed, visibility,
                       required_components_json, present_components_json,
                       missing_components_json, missing_decision_parts_json,
                       unwrapped_identifiers_json, unknown_identifiers_json,
                       missing_evidence_sources_json, inspection_errors_json,
                       inspection_ok, visual_smoke_errors_json
                FROM artifact_receipts_v3
                WHERE runtime=? AND project_hash=? AND session_id=? AND turn_id=?
                  AND expires_at > ?
                ORDER BY created_at_text, path
                """,
                (runtime, project_hash, session_id, turn_id, current),
            ).fetchall()
        return tuple(
            ArtifactReceipt(
                runtime=runtime,
                project_root=str(row[0]),
                session_id=session_id,
                turn_id=turn_id,
                path=str(row[1]),
                sha256=str(row[2]),
                bytes=int(row[3]),
                created_at=str(row[4]),
                gloss_check=str(row[5]),
                glossary_sha256=str(row[6]),
                glossary_source=str(row[7]),
                visual_smoke=str(row[8]),
                previewed=bool(row[9]),
                visibility=str(row[10]),
                required_components=_json_tuple(row[11]),
                present_components=_json_tuple(row[12]),
                missing_components=_json_tuple(row[13]),
                missing_decision_parts=_json_tuple(row[14]),
                unwrapped_identifiers=_json_tuple(row[15]),
                unknown_identifiers=_json_tuple(row[16]),
                missing_evidence_sources=_json_tuple(row[17]),
                inspection_errors=_json_tuple(row[18]),
                inspection_ok=bool(row[19]),
                visual_smoke_errors=_json_tuple(row[20]),
            )
            for row in rows
        )

    def save_plan(
        self,
        *,
        runtime: str,
        project_hash: str,
        session_id: str,
        turn_id: str,
        plan: ExplanationPlan,
        ttl_seconds: int,
        now: float | None = None,
    ) -> None:
        current = time.time() if now is None else now
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    """
                    INSERT INTO preflight_plans (
                        runtime, project_hash, session_id, turn_id,
                        audience, depth, components_json, reasons_json,
                        provisional, should_continue, delivery, publish_policy,
                        deprecated_aliases_json, created_at, expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(runtime, project_hash, session_id, turn_id)
                    DO UPDATE SET
                        audience=excluded.audience,
                        depth=excluded.depth,
                        components_json=excluded.components_json,
                        reasons_json=excluded.reasons_json,
                        provisional=excluded.provisional,
                        should_continue=excluded.should_continue,
                        delivery=excluded.delivery,
                        publish_policy=excluded.publish_policy,
                        deprecated_aliases_json=excluded.deprecated_aliases_json,
                        created_at=excluded.created_at,
                        expires_at=excluded.expires_at
                    """,
                    (
                        runtime,
                        project_hash,
                        session_id,
                        turn_id,
                        plan.audience,
                        plan.depth,
                        json.dumps(plan.components, ensure_ascii=False),
                        json.dumps(plan.reason_codes, ensure_ascii=False),
                        int(plan.provisional),
                        int(plan.should_continue),
                        plan.delivery,
                        plan.publish_policy,
                        json.dumps(plan.deprecated_aliases, ensure_ascii=False),
                        current,
                        current + ttl_seconds,
                    ),
                )

    def load_plan(
        self,
        *,
        runtime: str,
        project_hash: str,
        session_id: str,
        turn_id: str,
        now: float | None = None,
    ) -> ExplanationPlan | None:
        current = time.time() if now is None else now
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT audience, depth, components_json, reasons_json,
                       provisional, should_continue, delivery, publish_policy,
                       deprecated_aliases_json
                FROM preflight_plans
                WHERE runtime=? AND project_hash=? AND session_id=? AND turn_id=?
                  AND expires_at > ?
                """,
                (runtime, project_hash, session_id, turn_id, current),
            ).fetchone()
        if row is None:
            return None
        return ExplanationPlan(
            audience=str(row[0]),
            depth=str(row[1]),
            components=tuple(json.loads(row[2])),
            reason_codes=tuple(json.loads(row[3])),
            provisional=bool(row[4]),
            should_continue=bool(row[5]),
            delivery=str(row[6]),
            publish_policy=str(row[7]),
            deprecated_aliases=_json_tuple(row[8]),
        )

    def load_plan_created_at(
        self,
        *,
        runtime: str,
        project_hash: str,
        session_id: str,
        turn_id: str,
        now: float | None = None,
    ) -> float | None:
        """その回の「依頼を受けた時刻」（予告の計画を保存した epoch 秒）を返す。無い・期限切れは None。

        2026-10-08：回の開始時刻は保存してあった（preflight_plans.created_at）のに、読む口が
        無かった。回答集めのシート（sheets.py）を「この回に書かれたもの」だけに絞るのに使う。
        ⚠️load_plan の返り値（ExplanationPlan）は変えない＝別の口として足した。
        """
        current = time.time() if now is None else now
        with closing(self._connect()) as connection:
            row = connection.execute(
                """
                SELECT created_at
                FROM preflight_plans
                WHERE runtime=? AND project_hash=? AND session_id=? AND turn_id=?
                  AND expires_at > ?
                """,
                (runtime, project_hash, session_id, turn_id, current),
            ).fetchone()
        if row is None:
            return None
        try:
            return float(row[0])
        except (TypeError, ValueError):
            return None

    def claim_response(
        self,
        *,
        runtime: str,
        project_hash: str,
        session_id: str,
        turn_id: str,
        response_sha256: str,
        ttl_seconds: int,
        now: float | None = None,
    ) -> bool:
        current = time.time() if now is None else now
        expires_at = current + ttl_seconds
        with closing(self._connect()) as connection:
            with connection:
                connection.execute(
                    "DELETE FROM explanation_plans WHERE expires_at <= ?", (current,)
                )
                cursor = connection.execute(
                    """
                    INSERT OR IGNORE INTO explanation_plans (
                        runtime,
                        project_hash,
                        session_id,
                        turn_id,
                        response_sha256,
                        created_at,
                        expires_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        runtime,
                        project_hash,
                        session_id,
                        turn_id,
                        response_sha256,
                        current,
                        expires_at,
                    ),
                )
                inserted = cursor.rowcount == 1
        return inserted
