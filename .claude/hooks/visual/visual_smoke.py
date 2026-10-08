from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


def _default_playwright_browsers_root() -> Path:
    """Playwrightのブラウザ本体の既定の置き場（2026-09-25・OSごとに分岐）。

    優先順位＝①環境変数 PLAYWRIGHT_BROWSERS_PATH（Playwright自身が最優先で見る値。
    どのOSでも通用する）②OSごとの既定：Windows＝`%LOCALAPPDATA%/ms-playwright`、
    macOS＝`~/Library/Caches/ms-playwright`、Linux＝`~/.cache/ms-playwright`。
    ⚠️Windowsでの既定はこれまでと1バイトも変えない。
    """
    root_env = os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "")
    if root_env:
        return Path(root_env)
    if sys.platform == "win32":
        return Path(os.environ.get("LOCALAPPDATA", "")) / "ms-playwright"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "ms-playwright"
    return Path.home() / ".cache" / "ms-playwright"


def _default_npx_cache_root() -> Path | None:
    """npxがパッケージを展開するキャッシュの既定の置き場（2026-09-25・OSごとに分岐）。

    優先順位＝①環境変数 npm_config_cache（npmが実際に使っているキャッシュの根。
    どのOSでも通用する）②OSごとの既定：Windows＝`%LOCALAPPDATA%/npm-cache`、
    それ以外（macOS・Linux）＝`~/.npm`。どちらも下の `_npx` を見る。
    ⚠️Windowsでの既定はこれまでと1バイトも変えない。見つからなければ None
    （呼び出し側はPlaywrightが無いものとして扱う）。
    """
    npm_cache = os.environ.get("npm_config_cache", "")
    if npm_cache:
        return Path(npm_cache) / "_npx"
    if sys.platform == "win32":
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        if not local_app_data:
            return None
        return Path(local_app_data) / "npm-cache" / "_npx"
    return Path.home() / ".npm" / "_npx"


def _npm_config_cache_root() -> Path | None:
    """npm 自身に聞いたキャッシュの置き場の下の `_npx`（2026-09-25 新設）。

    既定の置き場（`_default_npx_cache_root`）で Playwright が見つからないときだけ使う。
    実測＝GitHub の Windows の実行環境は npm のキャッシュを設定ファイル（npmrc）で
    別の場所にしており、環境変数にも既定の場所にも無かった。Windows の npm は `npm.cmd`
    なので、名前の解決は shutil.which に任せる。見つからない・失敗したら None。
    """
    npm = shutil.which("npm")
    if not npm:
        return None
    try:
        completed = subprocess.run(
            [npm, "config", "get", "cache"],
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    value = completed.stdout.strip() if completed.returncode == 0 else ""
    if not value:
        return None
    return Path(value) / "_npx"


@dataclass(frozen=True)
class VisualSmokeResult:
    status: str
    errors: tuple[str, ...]
    metrics: Mapping[str, Any]


NODE_SMOKE_SCRIPT = r"""
const { pathToFileURL } = require('url');
const playwrightPath = process.argv[1];
const artifactPath = process.argv[2];
const artifactUrl = pathToFileURL(artifactPath).href;
const { chromium } = require(playwrightPath);
(async () => {
  const browser = await chromium.launch({headless:true});
  const errors = [];
  const metrics = {viewports:{}, externalRequests:0};
  const viewports = [[1280,900],[390,844]];
  try {
    for (const [width,height] of viewports) {
      const page = await browser.newPage({viewport:{width,height}});
      const key = `${width}x${height}`;
      const pageErrors = [];
      page.on('pageerror', error => pageErrors.push(`pageerror:${String(error).slice(0,180)}`));
      page.on('console', message => {
        if (message.type() === 'error') pageErrors.push(`console:${message.text().slice(0,180)}`);
      });
      await page.route('**/*', async route => {
        const url = route.request().url();
        if (url === artifactUrl || url.startsWith('data:') || url.startsWith('about:')) {
          await route.continue();
        } else {
          metrics.externalRequests += 1;
          pageErrors.push(`external-request:${url.slice(0,180)}`);
          await route.abort();
        }
      });
      await page.goto(artifactUrl, {waitUntil:'load', timeout:8000});
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
      if (overflow) pageErrors.push('horizontal-overflow');

      const tooltipCount = await page.locator('.t').count();
      let hoverVisible = null;
      let focusVisible = null;
      if (tooltipCount) {
        const tooltip = page.locator('.t').first();
        await tooltip.hover();
        hoverVisible = await tooltip.evaluate(el => getComputedStyle(el,'::after').display !== 'none');
        await tooltip.focus();
        focusVisible = await tooltip.evaluate(el => getComputedStyle(el,'::after').display !== 'none');
        if (!hoverVisible) pageErrors.push('tooltip-hover-hidden');
        if (!focusVisible) pageErrors.push('tooltip-focus-hidden');
        // 開いた吹き出しが頁を押し広げないかを見る。
        // ⚠️全部触ると重い（実測で実行器が落ちた）。危ない順＝右端に近い順に数個だけ。
        if (width >= 601) {
          const risky = await page.evaluate(() => {
            const out = [];
            document.querySelectorAll('.t').forEach((el, i) => {
              const rects = [...el.getClientRects()];
              if (!rects.length) return;
              out.push({i: i, edge: Math.max(...rects.map(r => r.right))});
            });
            out.sort((a, b) => b.edge - a.edge);
            return out.slice(0, 6).map(x => x.i);
          });
          for (const index of risky) {
            try {
              await page.locator('.t').nth(index).hover({timeout: 1500});
            } catch (error) {
              continue;
            }
            const grew = await page.evaluate(
              () => document.documentElement.scrollWidth > innerWidth
            );
            if (grew) { pageErrors.push('tooltip-overflow'); break; }
          }
        }
      }

      const decisionCount = await page.locator('section[data-component="decision"]').count();
      let decisionUpdated = null;
      let objectionUpdated = null;
      let selectAllWorked = null;
      if (decisionCount) {
        // 2026-08-29：選択肢は radio だけでなく checkbox のこともある（複数選べる形）。
        // ⚠️ここを radio 決め打ちにしていたため、複数選択の頁が「部品が無い」と誤判定された。
        const radio = page.locator('input[name=decision]').first();
        const prompt = page.locator('#decision-prompt');
        if (!await radio.count() || !await prompt.count()) {
          pageErrors.push('decision-controls-missing');
        } else {
          await radio.check();
          // 2026-10-08：回答文は初期表示から「(未選択 = お任せ…)」の固定形になった（初期文で判定できない）。
          // ∴押した選択肢の文が回答文に入ったかで見る（script が死ねば初期のまま＝落ちる）。
          const pickedLabel = (await radio.getAttribute('data-label')) || '';
          const promptAfterPick = (await prompt.textContent()) || '';
          decisionUpdated = !promptAfterPick.includes('選択してください')
            && (!pickedLabel || promptAfterPick.includes(pickedLabel));
          if (!decisionUpdated) pageErrors.push('decision-prompt-not-updated');

          const objectionText = page.locator('textarea[name=objection],textarea#decision-objection').first();
          const objectionCheck = page.locator('input[name=objection]').first();
          if (await objectionText.count()) {
            await objectionText.fill('追加条件');
            await objectionText.dispatchEvent('input');
            objectionUpdated = (await prompt.textContent() || '').includes('追加条件');
          } else if (await objectionCheck.count()) {
            await objectionCheck.check();
            const promptAfterObjection = (await prompt.textContent()) || '';
            objectionUpdated = promptAfterObjection.includes('異議.') || promptAfterObjection.includes('これは違う');
          } else {
            objectionUpdated = false;
          }
          if (!objectionUpdated) pageErrors.push('objection-prompt-not-updated');

          const select = page.locator('#select-decision,[data-role="select-all"]').first();
          if (await select.count()) {
            await select.click();
            selectAllWorked = await page.evaluate(() => String(getSelection()).length > 0);
          } else {
            selectAllWorked = false;
          }
          if (!selectAllWorked) pageErrors.push('select-all-failed');
        }
      }
      // 2026-09-26（見やすさ V1）：文字と背景のコントラストを数える（WCAG の基準＝小さな字は4.5、
      // 大きな字は3）。止めはしない＝数を返すだけ（render_page.py が知らせる）。
      const contrast = await page.evaluate(() => {
        const parse = c => {
          const s = String(c); const i = s.indexOf('('); const j = s.indexOf(')');
          if (i < 0 || j < 0) return null;
          const p = s.slice(i + 1, j).split(/[ ,/]+/).filter(Boolean).map(Number);
          return {r: p[0], g: p[1], b: p[2], a: p.length > 3 ? p[3] : 1};
        };
        const lum = c => {
          const f = v => { v = v / 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
          return 0.2126 * f(c.r) + 0.7152 * f(c.g) + 0.0722 * f(c.b);
        };
        const bgOf = el => {
          for (let e = el; e; e = e.parentElement) {
            const c = parse(getComputedStyle(e).backgroundColor);
            if (c && c.a > 0.5) return c;
          }
          return {r: 255, g: 255, b: 255, a: 1};
        };
        let low = 0, min = 99;
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        for (let n = walker.nextNode(); n; n = walker.nextNode()) {
          if (!n.textContent.trim()) continue;
          const el = n.parentElement;
          if (!el || el.closest('svg') || el.offsetParent === null) continue;
          const cs = getComputedStyle(el); const fg = parse(cs.color);
          if (!fg) continue;
          const bg = bgOf(el); const a = lum(fg), b = lum(bg);
          const ratio = (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
          const size = parseFloat(cs.fontSize); const bold = parseInt(cs.fontWeight, 10) >= 700;
          const large = size >= 24 || (bold && size >= 18.66);
          if (ratio < (large ? 3 : 4.5)) low += 1;
          if (ratio < min) min = ratio;
        }
        return {low, min: Math.round(min * 100) / 100};
      });
      metrics.viewports[key] = {
        lowContrast: contrast.low,
        minContrast: contrast.min,
        overflow,
        tooltipCount,
        hoverVisible,
        focusVisible,
        decisionCount,
        decisionUpdated,
        objectionUpdated,
        selectAllWorked,
        errorCount:pageErrors.length,
      };
      errors.push(...pageErrors.map(error => `${key}:${error}`));
      await page.close();
    }
  } finally {
    await browser.close();
  }
  console.log(JSON.stringify({status:errors.length ? 'fail' : 'pass', errors, metrics}));
})().catch(error => {
  console.log(JSON.stringify({status:'fail',errors:[`browser-smoke:${String(error).slice(0,180)}`],metrics:{}}));
  process.exitCode = 1;
});
"""


def _bounded_errors(values: object) -> tuple[str, ...]:
    if not isinstance(values, list):
        return ("visual smoke returned malformed errors",)
    return tuple(str(value)[:240] for value in values[:20] if str(value).strip())


def _browser_installed_for(candidate: str) -> bool:
    # candidate（…/node_modules/playwright）が要求する chromium-headless-shell の版が手元にあるか。
    # 要求版＝隣の playwright-core/browsers.json。置き場＝_default_playwright_browsers_root()
    # （PLAYWRIGHT_BROWSERS_PATH か、OSごとの既定）。
    # 読めない・見つからないときは False（＝その版を後回しにするだけで、失敗にはしない）。
    core = Path(candidate).parent / "playwright-core" / "browsers.json"
    try:
        data = json.loads(core.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    root = _default_playwright_browsers_root()
    browsers = data.get("browsers", []) if isinstance(data, dict) else []
    for browser in browsers:
        if isinstance(browser, dict) and browser.get("name") == "chromium-headless-shell":
            revision = str(browser.get("revision", "")).strip()
            return bool(revision) and (root / ("chromium_headless_shell-" + revision)).is_dir()
    return False


def _resolve_playwright() -> tuple[str | None, str | None]:
    try:
        resolved = subprocess.run(
            ["node", "-p", "require.resolve('playwright')"],
            text=True,
            encoding="utf-8",
            capture_output=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        resolved = None
    if resolved is not None and resolved.returncode == 0 and resolved.stdout.strip():
        return resolved.stdout.strip(), None

    # 既定の置き場で見つからないときだけ、npm 自身に置き場を聞く（2026-09-25）。
    for root_getter in (_default_npx_cache_root, _npm_config_cache_root):
        npx_cache_root = root_getter()
        if npx_cache_root is None:
            continue
        pattern = str(npx_cache_root / "*" / "node_modules" / "playwright")
        candidates = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)
        existing = [c for c in candidates[:20] if Path(c).is_dir() or Path(c).is_file()]
        # 2026-09-06：更新時刻の新しい順の先頭を無条件に選ぶと、別作業が npx で落とした新しい版（ブラウザ未取得）に
        # 当たって「visual smoke runner failed」になる（実害＝1.63.0-alpha が 1243 を要求・手元は 1234 まで）。
        # ∴要求するブラウザが手元にある版を先に選び、無ければ従来どおり先頭に倒す。
        for candidate in existing:
            if _browser_installed_for(candidate):
                return candidate, None
        for candidate in existing:
            return candidate, None
    return None, "Playwright is not installed"


def _run_node(command: list[str], *, timeout_seconds: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        text=True,
        encoding="utf-8",
        capture_output=True,
        timeout=timeout_seconds,
        check=False,
        shell=False,
    )


def run_visual_smoke(
    path: str | Path,
    *,
    timeout_seconds: int = 12,
) -> VisualSmokeResult:
    artifact = Path(path).resolve()
    if not artifact.is_file() or artifact.suffix.lower() != ".html":
        return VisualSmokeResult("fail", ("artifact path is not an existing HTML file",), {})

    playwright_path, resolution_error = _resolve_playwright()
    if not playwright_path:
        return VisualSmokeResult("not_run", (resolution_error or "Playwright unavailable",), {})

    command = ["node", "-e", NODE_SMOKE_SCRIPT, playwright_path, str(artifact)]
    try:
        completed = _run_node(command, timeout_seconds=max(1, int(timeout_seconds)))
    except subprocess.TimeoutExpired:
        return VisualSmokeResult("fail", ("visual smoke timed out",), {})
    except OSError:
        return VisualSmokeResult("fail", ("visual smoke runner could not start",), {})

    if completed.returncode != 0:
        return VisualSmokeResult("fail", ("visual smoke runner failed",), {})
    try:
        payload = json.loads(completed.stdout.strip())
    except (TypeError, json.JSONDecodeError):
        return VisualSmokeResult("fail", ("visual smoke returned malformed JSON",), {})
    if not isinstance(payload, dict):
        return VisualSmokeResult("fail", ("visual smoke returned malformed payload",), {})

    status = str(payload.get("status") or "fail")
    if status not in {"pass", "fail"}:
        status = "fail"
    errors = _bounded_errors(payload.get("errors", []))
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), dict) else {}
    if status == "pass" and errors:
        status = "fail"
    return VisualSmokeResult(status, errors, metrics)
