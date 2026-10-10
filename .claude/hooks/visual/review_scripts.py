"""説明の頁に載せる「指摘」と「添削」の画面の script と CSS（2026-10-09）。

出所：akapen 0.2.0（MIT）の assets/shiteki/kit-template.html と assets/tensaku/template.html から移植。

検品の Gate は頁の script を「判断欄・指摘・添削」の3本のどれかとの完全一致でしか認めない。
だからこのファイルの定数がそのまま頁に入る（render_components が並べる）。

境目の名前：
  CHIPS               指摘の札7種（akapen の指摘 kit と同じ順・同じ文字）
  ROLE_ORDER          script の並び（判断欄が必ず先）
  SHITEKI_SCRIPT      指摘の画面（単位＝`[data-blk]` の要素）
  TENSAKU_SCRIPT      添削の画面（`#ms-source` がある原稿の頁と、無い説明の頁の2つの使い方）
  REVIEW_CSS_SHITEKI  指摘の CSS（共通の部分を含む）
  REVIEW_CSS_TENSAKU  添削の CSS（共通の部分を含む）
  review_css(roles)   使う役割に合わせた CSS（共通の部分は1回だけ）
  normalize_mode      定義の `review` の値を none｜shiteki｜tensaku｜both にそろえる
  roles_for_mode      mode から載せる役割の組

作りの決まり（全部、script と CSS の中身の注意）：
- この script は window.pageReply（判断欄の script が作る）に頼る。無ければ何もしない。
  回答文の「## 指摘」「## 添削」の見出しと並びは pageReply.compose が足す＝ここは本文の行だけを返す。
- 説明の頁の赤ペンは「入れたときだけ」動く。右下の帯 #rv-bar の釦で body.dataset.rv（空｜shiteki｜tensaku）
  を切り替え、切り替えたら document に rv:mode を投げる。排他。Esc で切る。
  原稿の頁（section[data-component="manuscript"] の data-review-mode）では最初から入っている。
- 番号 data-blk は Python が振る（JS は振り直さない）。印（#N の丸）は CSS の擬似要素で出す
  ＝頁の DOM も innerText も汚さない。
- 色は頁のトークンだけ。z-index は 1200 以上。印刷では帯・板・引き出しを隠す。
- 検品の外部依存の判定（receipts.py）に触れる文字を書かない：
  http・https・file の頭の文字列、fetch・XMLHttpRequest・WebSocket・EventSource・sendBeacon、
  url( ・@import、src・href・action に「=」が続く形（変数名も不可＝src= を避ける）、
  javascript: 。ダウンロードは Blob の URL を作る必要があるので入れていない。
- JS の中に注釈を書かない（毎回の頁のバイトになる）。説明は上のこの文書と Python 側の注釈に置く。
- 添削の原稿の使い方は、ブロックの分け方（parseBlocks）を akapen のまま移している。
  Python 側の markdown_lite.parse_blocks と番号が一致する前提（ブロック数と型が合わないときは
  Python が描いた HTML を使わず、JS で全部描き直す）。
- 捨てたもの（akapen との違い）：固定の頭と脚・結論の箱・赤入れ量の統計・一言メモ・表のセルごとの
  入力欄（表は Markdown のまま直す）・メタ情報の表示切り替え・ダウンロード・Google Fonts。
  差分で「描画に出ない変更」は、その直しの全体を1行で出す簡易版にした。
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

CHIPS = (
    "削る",
    "短くする",
    "言い換える",
    "事実を確認",
    "図を直す",
    "順序を入れ替える",
    "ここは良い",
)

ROLE_ORDER = ("decision", "shiteki", "tensaku")

_MODES = ("none", "shiteki", "tensaku", "both")


def normalize_mode(value: Any) -> str:
    """定義の `review`（文字列か `{"mode": …}`）を none｜shiteki｜tensaku｜both にそろえる。

    未知の値・空・None・False は none。True は both（「付ける」とだけ書いた定義）。
    """
    if isinstance(value, Mapping):
        value = value.get("mode")
    if value is True:
        return "both"
    if isinstance(value, str):
        text = value.strip().lower()
        if text in _MODES:
            return text
    return "none"


def roles_for_mode(mode: Any) -> tuple[str, ...]:
    """mode から、頁に載せる script の役割を ROLE_ORDER の順で返す（判断欄は含めない）。"""
    normalized = normalize_mode(mode)
    if normalized == "both":
        return ("shiteki", "tensaku")
    if normalized in ("shiteki", "tensaku"):
        return (normalized,)
    return ()


def _chips_js() -> str:
    return "[" + ",".join('"' + chip + '"' for chip in CHIPS) + "]"


def _wrap(body: str) -> str:
    return "(function(){\n'use strict';\n" + body + "})();"


_KIT_JS = r"""const B=document.body,R=window.pageReply;
if(!R)return;
const $=i=>document.getElementById(i);
const MS=document.querySelector('section[data-component="manuscript"]');
const MODE=MS?MS.dataset.reviewMode||'':'';
function mk(g,c,x){const e=document.createElement(g);if(c)e.className=c;if(x!=null)e.textContent=x;return e;}
function btn(c,x,f,i){const e=mk('button','rv-btn'+(c?' '+c:''),x);e.type='button';if(i)e.id=i;if(f)e.addEventListener('click',f);return e;}
function bar(){let b=$('rv-bar');if(!b){b=mk('div','rv-ui');b.id='rv-bar';b.setAttribute('role','toolbar');b.setAttribute('aria-label','指摘と添削');B.appendChild(b);}return b;}
function put(e){const b=bar(),c=$('rv-compose');if(c&&c.parentNode===b)b.insertBefore(e,c);else b.appendChild(e);}
const outOpen=()=>{const o=$('rv-out');return!!o&&!o.hidden;};
function vis(){const b=bar();b.hidden=![...b.children].some(c=>!c.hidden);}
function setRv(m){B.dataset.rv=B.dataset.rv===m?'':m;document.dispatchEvent(new CustomEvent('rv:mode'));}
function tabs(){const o=!!B.dataset.rv||MODE==='shiteki';document.querySelectorAll('[data-blk]').forEach(u=>{if(o){if(!u.hasAttribute('tabindex')){u.setAttribute('tabindex','0');u.setAttribute('data-rv-tab','');}}else if(u.hasAttribute('data-rv-tab')){u.removeAttribute('tabindex');u.removeAttribute('data-rv-tab');}});}
const txt=el=>String(el.innerText||el.textContent||'').replace(/\s+/g,' ').trim();
const sig=u=>u.textContent.replace(/\s+/g,'').slice(0,16);
const cut=(s,n)=>s.length>n?s.slice(0,n)+'…':s;
function rd(k){try{return JSON.parse(localStorage.getItem(k)||'null');}catch(e){return null;}}
function wr(k,o){try{if(o==null)localStorage.removeItem(k);else localStorage.setItem(k,JSON.stringify(o));}catch(e){}}
function composeUI(){
if($('decision-prompt')||$('rv-compose'))return;
const c=btn('rv-main','貼り付ける文章を作る',null,'rv-compose');bar().appendChild(c);
const o=mk('div','rv-ui rv-out'),st=mk('p','rv-st'),ta=mk('textarea'),row=mk('div','rv-row');
o.id='rv-out';o.hidden=true;o.setAttribute('role','dialog');o.setAttribute('aria-label','貼り付ける文章');
ta.readOnly=true;ta.spellcheck=false;ta.setAttribute('aria-label','貼り付ける文章');
async function copy(){
ta.value=R.compose().join('\n');o.hidden=false;let ok=false;
try{if(navigator.clipboard&&window.isSecureContext!==false){await navigator.clipboard.writeText(ta.value);ok=true;}}catch(e){}
if(!ok){try{ta.focus();ta.select();ok=document.execCommand('copy');}catch(e){}}
st.textContent=ok?'コピーしました。Claude Code のターミナルに貼り付けて Enter してください。':'下の欄を選択してコピーし、Claude Code に貼り付けてください。';
if(!ok){try{ta.focus();ta.select();}catch(e){}}}
c.addEventListener('click',copy);
row.append(btn('','もう一度コピー',copy),mk('span','rv-sp'),btn('','閉じる',()=>{o.hidden=true;}));
o.append(st,ta,row);B.appendChild(o);
const rb=R.rebuild;R.rebuild=function(){rb();if(!o.hidden)ta.value=R.compose().join('\n');};
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&!o.hidden)o.hidden=true;});
}
function dfoot(d,close){if($('decision-prompt'))return;const f=mk('div','rv-dfoot');f.appendChild(btn('rv-main','貼り付ける文章を作る',()=>{close();const c=$('rv-compose');if(c)c.click();}));d.appendChild(f);}
"""

_SHITEKI_JS = r"""const KEY='uc-shiteki:'+document.title;
const CHIPS=__CHIPS__;
const fixed=MODE==='shiteki';
const on=()=>B.dataset.rv==='shiteki'||(fixed&&!B.dataset.rv);
const unit=n=>document.querySelector('[data-blk="'+n+'"]');
let S=rd(KEY);S=S&&Array.isArray(S.annos)?S:{annos:[]};
S.annos=S.annos.filter(a=>a&&typeof a.block==='number'&&unit(a.block)&&a.g===sig(unit(a.block)));
let cur=null,ei=null,chip=null,last=null;
const shade=mk('div','rv-ui rv-shade'),sheet=mk('div','rv-ui rv-sheet'),tg=mk('p','rv-target'),cs=mk('div','rv-chips'),nt=mk('textarea','rv-ta'),msg=mk('p','rv-msg'),row=mk('div','rv-row');
shade.hidden=sheet.hidden=true;sheet.setAttribute('role','dialog');sheet.setAttribute('aria-label','指摘を書く');
nt.placeholder='ここをこうして（自由に書く。札だけでもよい）';nt.setAttribute('aria-label','ひとこと');
const dl=btn('rv-danger','削除',()=>{if(ei!=null)S.annos.splice(ei,1);closeSheet();render();});
row.append(dl,mk('span','rv-sp'),btn('','キャンセル',closeSheet),btn('rv-main','保存',saveAnno));
sheet.append(tg,cs,nt,msg,row);
CHIPS.forEach(c=>{const b=btn('rv-chip',c,()=>{chip=chip===c?null:c;paint();});cs.appendChild(b);});
function paint(){[...cs.children].forEach(b=>{const o=b.textContent===chip;b.classList.toggle('on',o);b.setAttribute('aria-pressed',o);});}
function openSheet(t,i){cur=t;ei=i==null?null:i;const a=ei==null?null:S.annos[ei];chip=a?a.chip:null;paint();nt.value=a?a.note||'':'';msg.textContent='';
tg.textContent='';tg.appendChild(document.createTextNode('#'+t.block+' '));
if(t.quote){tg.appendChild(document.createTextNode('選択：'));tg.appendChild(mk('b','','「'+t.quote.slice(0,80)+'」'));}
else{const u=unit(t.block);tg.appendChild(document.createTextNode('対象：「'+cut(u?txt(u):'',60)+'」'));}
dl.hidden=ei==null;shade.hidden=false;sheet.hidden=false;setTimeout(()=>nt.focus(),50);}
function closeSheet(){shade.hidden=sheet.hidden=true;cur=null;ei=null;}
function saveAnno(){const n=nt.value.trim();if(!n&&!chip){msg.textContent='札を選ぶか、ひとこと書いてください。';return;}
const u=unit(cur.block),rec={block:cur.block,g:u?sig(u):'',quote:cur.quote||null,chip:chip,note:n,excerpt:cut(u?txt(u):'',80)};
if(ei!=null)S.annos[ei]=rec;else S.annos.push(rec);closeSheet();render();}
shade.addEventListener('click',closeSheet);
const dr=mk('div','rv-ui rv-drawer'),dh=mk('div','rv-dhead'),list=mk('div','rv-dbody');
dr.hidden=true;dr.setAttribute('role','dialog');dr.setAttribute('aria-label','指摘の一覧');
dh.append(mk('b','','指摘の一覧'),mk('span','rv-sp'),btn('','閉じる',closeDrawer));dr.append(dh,list);dfoot(dr,closeDrawer);
function openDrawer(){document.dispatchEvent(new CustomEvent('rv:drawer',{detail:'s'}));items();dr.hidden=false;}
function closeDrawer(){dr.hidden=true;}
document.addEventListener('rv:drawer',e=>{if(e.detail!=='s')closeDrawer();});
function order(){return S.annos.map((a,i)=>[a,i]).sort((x,y)=>x[0].block-y[0].block||x[1]-y[1]);}
function items(){list.textContent='';
if(!S.annos.length){list.appendChild(mk('p','rv-empty','まだ指摘はありません。「指摘する」を押してから、本文の塊を押すか、文字をなぞってください。'));return;}
order().forEach(([a,i])=>{const d=mk('div','rv-item'),u=unit(a.block);
d.appendChild(mk('p','rv-q','#'+a.block+' '+(a.quote?'「'+cut(a.quote,40)+'」':a.excerpt||'')));
const n=mk('p','rv-n');if(a.chip)n.appendChild(mk('span','rv-chipname','['+a.chip+']'));n.appendChild(document.createTextNode(a.note||''));d.appendChild(n);
const o=mk('div','rv-ops');
o.append(btn('rv-link','該当箇所へ',()=>{closeDrawer();if(u)u.scrollIntoView({behavior:'smooth',block:'center'});}),
btn('rv-link','編集',()=>{closeDrawer();openSheet({block:a.block,quote:a.quote},i);}),
btn('rv-link','削除',()=>{S.annos.splice(i,1);render();}));
d.appendChild(o);list.appendChild(d);});}
const tog=btn('','指摘する',()=>setRv('shiteki'),'rv-shiteki'),cnt=btn('','',openDrawer,'rv-s-count');
tog.setAttribute('aria-pressed','false');cnt.hidden=true;
if(!fixed)put(tog);put(cnt);
function render(){document.querySelectorAll('[data-rv-s]').forEach(u=>{u.removeAttribute('data-rv-s');});
document.querySelectorAll('[data-rv-p]').forEach(u=>{u.removeAttribute('data-rv-p');});
const by={};S.annos.forEach(a=>{by[a.block]=(by[a.block]||0)+1;});
Object.keys(by).forEach(k=>{const u=unit(k);if(!u)return;u.setAttribute('data-rv-s','');
const p=u.tagName==='TR'&&u.firstElementChild?u.firstElementChild:u;p.setAttribute('data-rv-p','#'+k+(by[k]>1?'×'+by[k]:''));});
cnt.textContent='指摘 '+S.annos.length+' 件';cnt.hidden=!S.annos.length;vis();items();wr(KEY,S.annos.length?S:null);R.rebuild();}
function sync(){const o=on();B.classList.toggle('rv-s',o);tog.setAttribute('aria-pressed',B.dataset.rv==='shiteki');tabs();if(!o){closeSheet();sb.hidden=true;}}
function lines(){return order().map(([a])=>{let s='#'+a.block;if(a.chip)s+=' ['+a.chip+']';
if(a.quote){const q=a.quote.replace(/\s+/g,' ').trim();s+=' 「'+cut(q,40)+'」';}
if(a.note)s+=' '+a.note.replace(/\s*\n\s*/g,' ').trim();return s;});}
R.extras.push({role:'shiteki',lines:lines,forget:()=>{S={annos:[]};closeSheet();render();}});
const sb=mk('button','rv-ui rv-sel','✎ 選択に赤入れ');sb.type='button';sb.hidden=true;
B.append(shade,sheet,dr,sb);
sb.addEventListener('mousedown',e=>e.preventDefault());
sb.addEventListener('click',()=>{sb.hidden=true;if(last)openSheet(last,null);});
document.addEventListener('selectionchange',()=>{
const s=getSelection();if(!on()||!s||s.isCollapsed||!s.rangeCount){sb.hidden=true;return;}
const r=s.getRangeAt(0),n=r.commonAncestorContainer,el=n.nodeType===1?n:n.parentElement;
if(!el||el.closest('.rv-ui')){sb.hidden=true;return;}
const u=el.closest('[data-blk]'),q=s.toString().replace(/\s+/g,' ').trim();
if(!u||q.length<2){sb.hidden=true;return;}
last={block:+u.dataset.blk,quote:q.slice(0,300)};
const b=r.getBoundingClientRect();sb.hidden=false;sb.style.top=(scrollY+b.bottom+8)+'px';sb.style.left=Math.max(8,Math.min(scrollX+b.left,innerWidth-150))+'px';});
document.addEventListener('click',e=>{
if(!on()||e.defaultPrevented)return;const g=e.target;
if(!g.closest||g.closest('.rv-ui,a,button,summary,input,textarea,label,select'))return;
const s=getSelection();if(s&&!s.isCollapsed)return;
const u=g.closest('[data-blk]');if(u)openSheet({block:+u.dataset.blk,quote:null},null);});
document.addEventListener('keydown',e=>{
if(e.key==='Escape'){if(outOpen())return;if(!sheet.hidden)closeSheet();else if(!dr.hidden)closeDrawer();else if(B.dataset.rv==='shiteki')setRv('shiteki');return;}
if(!on()||(e.key!=='Enter'&&e.key!==' '))return;
const u=e.target;if(u&&u.matches&&u.matches('[data-blk]')){e.preventDefault();openSheet({block:+u.dataset.blk,quote:null},null);}});
document.addEventListener('rv:mode',sync);
composeUI();render();sync();
"""

_TENSAKU_CORE_JS = r"""const sec=MS,ms=$('ms-source'),msMode=!!(sec&&ms&&MODE==='tensaku');
const D0='',D1='',I0='',I1='';
const isSent=c=>c>=''&&c<='';
const clean=s=>s.replace(/[-]/g,'');
const esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const oneLine=s=>s.replace(/\n/g,'⏎');
const qt=s=>'「'+cut(oneLine(s.trim()||s),80)+'」';
const TYPE_LABEL={heading:'見出し',paragraph:'段落',list:'箇条書き',table:'表',quote:'引用',code:'コード',hr:'区切り線',comment:'コメント'};
function charClass(c){
if(/[々㐀-鿿豈-﫿]/.test(c))return'k';
if(/[぀-ゟ]/.test(c))return'h';
if(/[゠-ヿｦ-ﾟ]/.test(c))return'K';
if(/[A-Za-z0-9０-９Ａ-Ｚａ-ｚ]/.test(c))return'a';
return's';}
function tokenize(str){
const out=[];let cur='',cc=null;
const push=()=>{if(!cur)return;if(cc==='h'&&cur.length>=2&&'とをがはにのでへも'.indexOf(cur[cur.length-1])>=0){out.push(cur.slice(0,-1));out.push(cur.slice(-1));}else out.push(cur);cur='';};
for(const c of str){const k=charClass(c);if(cur&&(k!==cc||k==='s'))push();cur+=c;cc=k;}
push();return out;}
function diffWords(a,b){
if(a===b){const s=a?[{eq:a,n:1}]:[];s.changed=0;return s;}
const A=tokenize(a),Bt=tokenize(b);
let p=0;while(p<A.length&&p<Bt.length&&A[p]===Bt[p])p++;
let q=0;while(q<A.length-p&&q<Bt.length-p&&A[A.length-1-q]===Bt[Bt.length-1-q])q++;
const X=A.slice(p,A.length-q),Y=Bt.slice(p,Bt.length-q),n=X.length,m=Y.length,W=m+1,ops=[];
for(let i=0;i<p;i++)ops.push(['=',A[i]]);
if(n*m>4e6){X.forEach(x=>ops.push(['-',x]));Y.forEach(y=>ops.push(['+',y]));}
else{const dp=new Uint16Array((n+1)*(m+1));
for(let i=n-1;i>=0;i--)for(let j=m-1;j>=0;j--)dp[i*W+j]=X[i]===Y[j]?dp[(i+1)*W+j+1]+1:Math.max(dp[(i+1)*W+j],dp[i*W+j+1]);
let i=0,j=0;
while(i<n&&j<m){if(X[i]===Y[j]){ops.push(['=',X[i]]);i++;j++;}else if(dp[(i+1)*W+j]>=dp[i*W+j+1]){ops.push(['-',X[i]]);i++;}else{ops.push(['+',Y[j]]);j++;}}
while(i<n)ops.push(['-',X[i++]]);
while(j<m)ops.push(['+',Y[j++]]);}
for(let i=A.length-q;i<A.length;i++)ops.push(['=',A[i]]);
const segs=[];let eq=[],del='',ins='';
const fC=()=>{if(del||ins){segs.push({del:del,ins:ins});del='';ins='';}};
const fE=()=>{if(eq.length){segs.push({eq:eq.join(''),n:eq.length});eq=[];}};
for(const [t,c] of ops){if(t==='='){fC();eq.push(c);}else{fE();if(t==='-')del+=c;else ins+=c;}}
fC();fE();
let raw=0;segs.forEach(s=>{if(s.eq===undefined)raw+=s.del.length+s.ins.length;});
let merged=true;
while(merged){merged=false;for(let k=1;k<segs.length-1;k++){const s=segs[k],p=segs[k-1],q=segs[k+1];
if(s.eq===undefined||p.eq!==undefined||q.eq!==undefined||s.n>1)continue;
const one=(!p.del!==!p.ins)&&(!q.del!==!q.ins)&&(!!p.del!==!!q.del);if(!one)continue;
segs.splice(k-1,3,{del:p.del+s.eq+q.del,ins:p.ins+s.eq+q.ins});merged=true;break;}}
for(let k=1;k<segs.length;k++){const s=segs[k],p=segs[k-1];
if(s.eq!==undefined||p.eq===undefined||(!!s.del===!!s.ins))continue;
const key=s.del?'del':'ins';let x=s[key],pe=p.eq,moved='';
while(x.length&&pe.length&&/\s/.test(x[x.length-1])&&pe[pe.length-1]===x[x.length-1]){const c=x[x.length-1];x=c+x.slice(0,-1);pe=pe.slice(0,-1);moved=c+moved;}
if(!moved)continue;
s[key]=x;p.eq=pe;
const q=segs[k+1];if(q&&q.eq!==undefined)q.eq=moved+q.eq;else segs.splice(k+1,0,{eq:moved,n:1});
if(!p.eq){segs.splice(k-1,1);k--;}}
segs.changed=raw;return segs;}
const nonEq=s=>s.filter(x=>x.eq===undefined);
const markedMd=segs=>segs.map(s=>s.eq!==undefined?s.eq:(s.del?D0+s.del+D1:'')+(s.ins?I0+s.ins+I1:'')).join('');
const segHtml=segs=>segs.map(s=>s.eq!==undefined?esc(s.eq):(s.del?'<del>'+esc(s.del)+'</del>':'')+(s.ins?'<ins>'+esc(s.ins)+'</ins>':'')).join('');
function blockText(h){const d=cut(oneLine(h.del.trim()||h.del),40),i=cut(oneLine(h.ins.trim()||h.ins),40);
if(h.del&&h.ins)return'「'+d+'」→「'+i+'」';if(h.del)return'「'+d+'」削除';return'「'+i+'」追加';}
function pairs(segs){return nonEq(segs).map(h=>{let d=h.del,i=h.ins;
if(!d||!i){const k=segs.indexOf(h),c=k>0&&segs[k-1].eq!==undefined?segs[k-1].eq.slice(-6):'';d=c+d;i=c+i;}
return qt(d)+'→'+qt(i);});}
function rawSegs(segs){
const rows=nonEq(segs).map(h=>{const k=segs.indexOf(h);
const pre=k>0&&segs[k-1].eq!==undefined?'<span class="rv-ctx">…'+esc(oneLine(segs[k-1].eq.slice(-12)))+'</span>':'';
const post=k+1<segs.length&&segs[k+1].eq!==undefined?'<span class="rv-ctx">'+esc(oneLine(segs[k+1].eq.slice(0,12)))+'…</span>':'';
return pre+(h.del?'<del>'+esc(cut(oneLine(h.del),120))+'</del>':'')+(h.ins?'<ins>'+esc(cut(oneLine(h.ins),120))+'</ins>':'')+post;});
return rows.length?'<div class="rv-raw"><span>Markdown の差分（描画には出ない変更）：</span>'+rows.join('<br>')+'</div>':'';}
function applyMarks(root){
const w=document.createTreeWalker(root,NodeFilter.SHOW_TEXT),nodes=[];
while(w.nextNode())nodes.push(w.currentNode);
let state=null;
nodes.forEach(tn=>{const text=tn.nodeValue;if(!state&&!/[-]/.test(text))return;
const frag=document.createDocumentFragment();let buf='';
const flush=()=>{if(!buf)return;if(state){const el=document.createElement(state);el.textContent=buf;frag.appendChild(el);}else frag.appendChild(document.createTextNode(buf));buf='';};
for(const ch of text){if(ch===D0){flush();state='del';}else if(ch===D1){flush();if(state==='del')state=null;}else if(ch===I0){flush();state='ins';}else if(ch===I1){flush();if(state==='ins')state=null;}else buf+=ch;}
flush();tn.parentNode.replaceChild(frag,tn);});}
"""

_TENSAKU_MD_JS = r"""const RE_HEADING=/^(#{1,6})(\s+|$)/,RE_FENCE=/^\s{0,3}(`{3,}|~{3,})(.*)$/,RE_HR=/^\s{0,3}(?:(?:-\s*){3,}|(?:\*\s*){3,}|(?:_\s*){3,})$/,RE_QUOTE=/^\s{0,3}>/,RE_ITEM=/^(\s*)([-*+]|\d{1,9}[.)])(\s+)(.*)$/,RE_TSEP=/^\s*\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)*\|?\s*$/,RE_COMMENT=/^\s{0,3}<\!--/;
const isBlank=l=>clean(l).trim()==='';
function lineType(cl,next){
if(RE_COMMENT.test(cl))return'comment';
if(RE_FENCE.test(cl))return'code';
if(RE_HEADING.test(cl))return'heading';
if(RE_HR.test(cl))return'hr';
if(RE_QUOTE.test(cl))return'quote';
if(RE_ITEM.test(cl))return'list';
if(cl.indexOf('|')>=0&&next!=null){const cn=clean(next);if(cn.indexOf('|')>=0&&RE_TSEP.test(cn))return'table';}
return'paragraph';}
function parseBlocks(text){
const endsNL=text.endsWith('\n'),lines=text.split('\n');
if(endsNL)lines.pop();
const n=lines.length,items=[];let head='',blanks=[],i=0;
while(i<n){
if(isBlank(lines[i])){blanks.push(lines[i]);i++;continue;}
if(items.length===0)head=blanks.map(b=>b+'\n').join('');else items[items.length-1].gap=blanks.map(b=>'\n'+b).join('')+'\n';
blanks=[];
const cl=clean(lines[i]),type=lineType(cl,i+1<n?lines[i+1]:null);
let j=i+1;
if(type==='code'){const fence=RE_FENCE.exec(cl)[1];
while(j<n){const c=clean(lines[j]).trim(),cm=/^(`{3,}|~{3,})\s*$/.exec(c);j++;if(cm&&cm[1][0]===fence[0]&&cm[1].length>=fence.length)break;}}
else if(type==='comment'){if(cl.indexOf('-'+'->')<0){while(j<n){const c=clean(lines[j]);j++;if(c.indexOf('-'+'->')>=0)break;}}}
else if(type==='heading'||type==='hr'){}
else if(type==='table'){while(j<n&&!isBlank(lines[j])&&clean(lines[j]).indexOf('|')>=0)j++;}
else if(type==='quote'){while(j<n&&!isBlank(lines[j])&&RE_QUOTE.test(clean(lines[j])))j++;}
else if(type==='list'){while(j<n&&!isBlank(lines[j])){const t=lineType(clean(lines[j]),j+1<n?lines[j+1]:null);if(t==='list'||t==='paragraph')j++;else break;}}
else{while(j<n&&!isBlank(lines[j])){const t=lineType(clean(lines[j]),j+1<n?lines[j+1]:null);if(t==='paragraph')j++;else break;}}
items.push({type:type,md:lines.slice(i,j).join('\n'),gap:''});
i=j;}
const tail=blanks.map(b=>'\n'+b).join('')+(endsNL?'\n':'');
if(items.length)items[items.length-1].gap=tail;else head+=tail;
return{head:head,items:items,endsNL:endsNL};}
function splitPrefix(raw,plen){let cnt=0,sent='',k=0;
while(k<raw.length&&cnt<plen){const ch=raw[k];if(isSent(ch))sent+=ch;else cnt++;k++;}
return sent+raw.slice(k);}
const plain=u=>u.replace(/^(?:https?|file):\/{2,3}/i,'');
function emph(s){
s=s.replace(/\*\*(?=\S)([\s\S]*?\S)\*\*/g,'<strong>$1</strong>');
s=s.replace(/__(?=\S)([\s\S]*?\S)__/g,'<strong>$1</strong>');
s=s.replace(/(^|[^*\w])\*(?=\S)([^*\n]*?\S)\*(?!\w)/g,'$1<em>$2</em>');
s=s.replace(/(^|[^_\w])_(?=\S)([^_\n]*?\S)_(?!\w)/g,'$1<em>$2</em>');
return s;}
function inline(s){
const ph=[],put=h=>{ph.push(h);return''+(ph.length-1)+'';};
s=s.replace(/(`+)(?!`)([\s\S]*?[^`])\1(?!`)/g,(m,f,c)=>put('<code>'+esc(c.replace(/^ (.+) $/,'$1'))+'</code>'));
s=s.replace(/!\[([^\]]*)\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g,(m,a)=>put('<span class="ms-img">[画像'+(a?': '+esc(clean(a)):'')+']</span>'));
s=s.replace(/\[([^\]]+)\]\(([^)\s]+)(?:\s+"[^"]*")?\)/g,(m,x,u)=>put('<span class="ms-link">'+emph(esc(x))+'</span><span class="ms-url">（'+esc(plain(clean(u)))+'）</span>'));
s=s.replace(/<(https?:\/\/[^\s<>]+)>/g,(m,u)=>put('<span class="ms-link">'+esc(plain(clean(u)))+'</span>'));
s=s.replace(/(^|[^A-Za-z0-9])(https?:\/\/[^\s<>]+)/g,(m,pre,u)=>{const x=u.replace(/[.,;:!?)）」』。、]+$/,'');return pre+put('<span class="ms-link">'+esc(plain(clean(x)))+'</span>')+u.slice(x.length);});
s=emph(esc(s));
s=s.replace(/ {2,}\n/g,'<br>');
let out=s;for(let k=0;k<6&&out.indexOf('')>=0;k++)out=out.replace(/(\d+)/g,(m,i)=>ph[+i]);
return out;}
function splitRow(raw){
let s=raw;const lm=/^[ \t-]*/.exec(s)[0],lead=lm.replace(/[ \t]/g,'');s=s.slice(lm.length);
if(s[0]==='|')s=s.slice(1);
const tm=/[ \t-]*$/.exec(s)[0],trail=tm.replace(/[ \t]/g,'');s=s.slice(0,s.length-tm.length);
if(s[s.length-1]==='|')s=s.slice(0,-1);
const cells=s.replace(/\\\|/g,'').split('|').map(c=>c.trim().replace(//g,'|'));
if(cells.length){cells[0]=lead+cells[0];cells[cells.length-1]=cells[cells.length-1]+trail;}
return cells;}
function renderTable(lines){
const head=splitRow(lines[0]),seps=splitRow(lines[1]).map(c=>clean(c).trim());
const align=seps.map(c=>/^:-+:$/.test(c)?'center':/^-+:$/.test(c)?'right':/^:-+$/.test(c)?'left':'');
const cols=head.length,cell=(g,x,c)=>'<'+g+(align[c]?' style="text-align:'+align[c]+'"':'')+'>'+inline(x)+'</'+g+'>';
let h='<div class="scroll"><table><thead><tr>';
for(let c=0;c<cols;c++)h+=cell('th',head[c],c);
h+='</tr></thead><tbody>';
for(let r=2;r<lines.length;r++){const row=splitRow(lines[r]);h+='<tr>';for(let c=0;c<cols;c++)h+=cell('td',row[c]==null?'':row[c],c);h+='</tr>';}
return h+'</tbody></table></div>';}
function renderList(lines){
const stack=[],roots=[];let last=null;
const lvl0=(indent,ordered,start)=>({indent:indent,ordered:ordered,start:start,items:[]});
for(let ln=0;ln<lines.length;ln++){
const raw=lines[ln],cl=clean(raw),m=RE_ITEM.exec(cl);
if(!m){if(last)last.text.push(clean(raw).length?splitPrefix(raw,(/^\s*/.exec(cl)||[''])[0].length):raw);continue;}
const indent=m[1].length,ordered=/\d/.test(m[2]),content=splitPrefix(raw,m[1].length+m[2].length+m[3].length);
while(stack.length&&indent<stack[stack.length-1].indent)stack.pop();
let lv;
if(!stack.length){lv=lvl0(indent,ordered,ordered?parseInt(m[2],10):1);roots.push(lv);stack.push(lv);}
else if(indent>stack[stack.length-1].indent&&stack[stack.length-1].items.length){lv=lvl0(indent,ordered,ordered?parseInt(m[2],10):1);const par=stack[stack.length-1].items;par[par.length-1].sub.push(lv);stack.push(lv);}
else lv=stack[stack.length-1];
last={text:[content],sub:[]};lv.items.push(last);}
if(!roots.length)return'';
function level(L){const g=L.ordered?'ol':'ul';let h='<'+g+(L.ordered&&L.start!==1?' start="'+L.start+'"':'')+'>';
L.items.forEach(it=>{h+='<li>'+inline(it.text.join('\n'))+it.sub.map(level).join('')+'</li>';});return h+'</'+g+'>';}
return roots.map(level).join('');}
function renderBlock(b){
const lines=b.md.split('\n');
switch(b.type){
case'heading':{const m=RE_HEADING.exec(clean(lines[0])),lv=m[1].length,c=splitPrefix(lines[0],m[0].length).replace(/\s+#+\s*$/,'');return'<h'+lv+'>'+inline(c)+'</h'+lv+'>';}
case'hr':return'<hr>';
case'comment':return'';
case'code':{const fm=RE_FENCE.exec(clean(lines[0]));let end=lines.length;
if(lines.length>1){const c=clean(lines[lines.length-1]).trim(),cm=/^(`{3,}|~{3,})\s*$/.exec(c);if(cm&&fm&&cm[1][0]===fm[1][0]&&cm[1].length>=fm[1].length)end=lines.length-1;}
const lang=(fm?fm[2]:'').trim().split(/\s+/)[0]||'';return'<pre><code'+(lang?' class="lang-'+esc(lang)+'"':'')+'>'+esc(lines.slice(1,end).join('\n'))+'</code></pre>';}
case'quote':{const inner=lines.map(l=>{const m=/^\s{0,3}>\s?/.exec(clean(l));return m?splitPrefix(l,m[0].length):l;}).join('\n');return'<blockquote>'+renderMd(inner)+'</blockquote>';}
case'table':return renderTable(lines);
case'list':return renderList(lines);
default:return'<p>'+inline(lines.map(l=>l.replace(/^ +/,'')).join('\n'))+'</p>';}}
function renderMd(md){return parseBlocks(md).items.map(renderBlock).join('');}
function safe(md){try{return renderMd(md);}catch(e){return'<pre>'+esc(clean(md))+'</pre>';}}
function docHtml(md){return parseBlocks(md).items.filter(b=>b.type!=='comment').map(b=>{let h;try{h=renderBlock(b);}catch(e){h='<pre>'+esc(clean(b.md))+'</pre>';}return'<div class="ms-blk">'+h+'</div>';}).join('');}
"""

_TENSAKU_MS_JS = r"""function manuscript(){
const host=sec.querySelector('article.ms');if(!host)return;
const KEY='uc-tensaku:'+document.title+':'+(ms.dataset.sha||'page');
const O=parseBlocks(ms.value.replace(/\r\n?/g,'\n'));
const pad=n=>String(n).padStart(3,'0');
const fresh=()=>O.items.map((b,i)=>({id:'b'+pad(i+1),o:i,f:b.md,g:b.gap,d:false}));
const S={items:fresh(),head:O.head,nn:1,ed:null,tab:'edit',draft:false,dirty:false};
const pre=[...host.querySelectorAll('.ms-blk')];
const snap=pre.length===O.items.length&&pre.every((e,i)=>+e.dataset.ms===i+1&&e.dataset.msType===O.items[i].type)?pre.map(e=>e.innerHTML):null;
const byId=id=>S.items.find(x=>x.id===id);
const draft=it=>it.o>=0?O.items[it.o].md:'';
const otype=it=>it.o>=0?O.items[it.o].type:null;
function typesOf(it){
if(it.d)return[otype(it)||'paragraph'];
if(it.f.trim()){const p=parseBlocks(it.f);if(p.items.length){const ts=[];p.items.forEach(b=>{if(ts.indexOf(b.type)<0)ts.push(b.type);});return ts;}}
return[otype(it)||'paragraph'];}
const typeOf=it=>typesOf(it)[0];
const typeLabel=it=>typesOf(it).map(x=>TYPE_LABEL[x]).join(' + ');
const cache=new Map();
function segsFor(it){const d=draft(it),f=it.d?'':it.f,c=cache.get(it.id);if(c&&c.d===d&&c.f===f)return c.s;const s=diffWords(d,f);cache.set(it.id,{d:d,f:f,s:s});return s;}
const chg=it=>segsFor(it).changed||0;
function finalMd(){const b=S.head+S.items.filter(x=>!x.d).map(x=>x.f+x.g).join('');return b.replace(/\s+$/,'')+(O.endsNL?'\n':'');}
function count(){return S.items.filter(it=>chg(it)>0).length;}
function save(){wr(KEY,{items:S.items.map(x=>({id:x.id,o:x.o,f:x.f,g:x.g,d:x.d})),head:S.head,nn:S.nn});}
(function(){const o=rd(KEY);if(!o||!Array.isArray(o.items))return;
const items=[],seen=new Set();
o.items.forEach(x=>{if(!x||typeof x.id!=='string'||!/^[bn]\d+$/.test(x.id)||typeof x.f!=='string'||seen.has(x.id))return;
const orig=Number.isInteger(x.o)&&x.o>=0&&x.o<O.items.length?x.o:-1;if(orig<0&&!x.f)return;
seen.add(x.id);items.push({id:x.id,o:orig,f:x.f,g:typeof x.g==='string'?x.g:'\n\n',d:!!x.d&&orig>=0});});
if(new Set(items.filter(x=>x.o>=0).map(x=>x.o)).size!==O.items.length)return;
S.items=items;S.head=typeof o.head==='string'?o.head:O.head;S.nn=Number.isInteger(o.nn)?o.nn:1;})();
const newId=()=>'n'+pad(S.nn++);
const tools=it=>{const hs=nonEq(segsFor(it));return'<div class="rv-tools"><span class="rv-badge">'+(it.o<0?'追加':'直された '+chg(it)+' 文字')+'</span><span class="rv-sum">'+esc(it.o<0?'ブロックを追加':hs.slice(0,3).map(blockText).join(' / ')+(hs.length>3?' / …':''))+'</span></div>';};
const lab=it=>it.o>=0?'段落 '+(it.o+1):'追加';
const lt=it=>{const t=typeLabel(it);return lab(it)+(it.o<0||t==='段落'?'':'・'+t);};
const snippet=(s,n)=>cut(clean(s).replace(/\s+/g,' ').trim(),n);
const addStrip=a=>'<div class="rv-addstrip"><button type="button" class="rv-addbtn" data-after="'+a+'">＋ ここに段落を足す</button></div>';
function attrs(it,ty){return' data-id="'+it.id+'"'+(it.o>=0?' data-ms="'+(it.o+1)+'" data-blk="'+(it.o+1)+'"':'')+' data-ms-type="'+ty+'"';}
function blkHtml(it){
const n=chg(it),ty=typeOf(it);let inner;
if(ty==='comment'&&it.o>=0&&it.f===draft(it))return'<div class="ms-blk" hidden'+attrs(it,ty)+'></div>';
if(n){inner=it.o<0?safe(I0+it.f+I1):diffRender(it).html;}
else if(snap&&it.o>=0&&it.f===draft(it))inner=snap[it.o];
else inner=safe(it.f);
return'<div class="ms-blk rv-b'+(n?' rv-chg':'')+'"'+attrs(it,ty)+' tabindex="0" title="クリックで直す（'+esc(lt(it))+'）">'+(n?tools(it):'')+'<span class="rv-pen">✎ 直す</span>'+inner+'</div>';}
function delHtml(it){return'<div class="ms-blk rv-b rv-delrow"'+attrs(it,otype(it)||'paragraph')+'><div class="rv-tools"><span class="rv-badge">削除・直された '+chg(it)+' 文字</span><span>'+esc(lt(it))+'</span><span class="rv-snip">'+esc(snippet(draft(it),80))+'</span><button type="button" class="rv-btn rv-sm" data-act="undelete">元に戻す</button></div></div>';}
function diffRender(it){
const segs=segsFor(it),m=markedMd(segs);
const a=parseBlocks(it.f).items.map(b=>b.type).join(),b=parseBlocks(clean(m)).items.map(x=>x.type).join();
if(a!==b)return{html:safe(it.f)+rawSegs(segs),raw:true};
return{html:safe(m),raw:false};}
function marks(root,sel){root.querySelectorAll(sel).forEach(el=>{applyMarks(el);const it=byId(el.dataset.id);
if(it&&it.o>=0&&!it.d&&!el.querySelector('del,ins')&&chg(it)&&!el.querySelector('.rv-raw'))el.insertAdjacentHTML('beforeend',rawSegs(segsFor(it)));});}
function autosize(ta){ta.style.height='auto';ta.style.height=Math.min(ta.scrollHeight+2,Math.round(innerHeight*0.7))+'px';}
function structWarn(it){
if(!it.f.trim())return'';
const ot=otype(it),ts=typesOf(it);
if(ot&&ot!=='paragraph'&&ot!=='comment'&&ts.indexOf(ot)<0)return'元は「'+TYPE_LABEL[ot]+'」でしたが、いまは「'+ts.map(x=>TYPE_LABEL[x]).join(' + ')+'」として描画されます。行頭の記号を確かめてください。';
return'';}
function buildEditor(it){
const sec2=mk('div','ms-blk rv-b rv-editing');sec2.dataset.id=it.id;
const ty=typeOf(it);
const tip=ty==='table'?'表は行ごとに「|」でつなぐ。行や列の足し引きもここで直す':ty==='list'?'行頭の「-」や「1.」は残す（1行=1項目）':ty==='quote'?'行頭の「>」は残す':'';
sec2.innerHTML='<div class="rv-edhead"><span class="rv-edtype"></span><span class="rv-badge rv-edbadge"></span><span class="rv-sp"></span><span class="rv-hint">Esc=取消・Ctrl+Enter=確定</span></div>'
+'<div class="rv-pair"><div class="rv-srcbox"><p class="rv-lbl">Markdown（ここを書き換える）'+(tip?'<span> ・'+esc(tip)+'</span>':'')+'</p><textarea class="rv-ta rv-edta" spellcheck="false" aria-label="ブロックの Markdown を書き換える"></textarea><p class="rv-warn"></p></div>'
+'<div class="rv-prevbox"><p class="rv-lbl"><button type="button" class="rv-btn rv-sm" data-mode="render">プレビュー</button><button type="button" class="rv-btn rv-sm" data-mode="diff">差分</button></p><div class="rv-prev ms"></div></div></div>'
+'<div class="rv-row"><button type="button" class="rv-btn rv-main" data-act="commit">確定</button><button type="button" class="rv-btn" data-act="cancel">取消</button><span class="rv-sp"></span><button type="button" class="rv-btn" data-act="addbelow">＋ この下に段落を足す</button><button type="button" class="rv-btn rv-danger" data-act="delete">削除</button></div>';
const ta=sec2.querySelector('.rv-edta');ta.value=it.f;
ta.addEventListener('input',()=>{it.f=ta.value.replace(/\r\n?/g,'\n');autosize(ta);refreshPreview();after();});
sec2.addEventListener('keydown',e=>{if(e.defaultPrevented)return;if(e.key==='Escape'){e.preventDefault();cancelEdit();}else if(e.key==='Enter'&&(e.metaKey||e.ctrlKey)){e.preventDefault();commitEdit();}});
return sec2;}
function refreshPreview(){
if(!S.ed)return;const it=byId(S.ed.id),el=host.querySelector('.rv-editing');if(!it||!el)return;
const body=el.querySelector('.rv-prev'),mode=S.ed.mode||'render';
el.querySelectorAll('[data-mode]').forEach(b=>b.classList.toggle('rv-on',b.dataset.mode===mode));
if(!it.f.trim())body.innerHTML='<span class="rv-ph">（空。このまま確定するとブロックは削除されます）</span>';
else if(mode==='diff'){const r=diffRender(it);body.innerHTML=r.html;applyMarks(body);if(!r.raw&&chg(it)&&!body.querySelector('del,ins'))body.insertAdjacentHTML('beforeend',rawSegs(segsFor(it)));}
else body.innerHTML=safe(it.f);
el.querySelector('.rv-warn').textContent=structWarn(it);
const n=chg(it),bd=el.querySelector('.rv-edbadge');bd.className='rv-badge rv-edbadge'+(n?' rv-on':'');bd.textContent=n?'直された '+n+' 文字':'無修正';
el.querySelector('.rv-edtype').textContent=lt(it);}
function renderEdit(){
const h=[addStrip('')];
S.items.forEach(it=>{
if(S.ed&&S.ed.id===it.id)h.push('<div id="rv-slot"></div>');
else if(it.d)h.push(delHtml(it));
else h.push(blkHtml(it));
h.push(addStrip(it.id));});
host.innerHTML=h.join('');
marks(host,'.ms-blk.rv-chg');
if(S.ed){const it=byId(S.ed.id),slot=$('rv-slot');if(it&&slot){const e=buildEditor(it);slot.replaceWith(e);autosize(e.querySelector('.rv-edta'));refreshPreview();}else S.ed=null;}}
function openEdit(id){
if(S.ed){if(S.ed.id===id)return;commitEdit(true);}
const it=byId(id);if(!it||it.d)return;
S.ed={id:id,before:it.f,isNew:false,mode:chg(it)?'diff':'render'};renderEdit();
const e=host.querySelector('.rv-editing');if(e){const ta=e.querySelector('.rv-edta');try{ta.focus({preventScroll:true});}catch(x){ta.focus();}e.scrollIntoView({block:'nearest'});}}
function commitEdit(silent){
const ed=S.ed;if(!ed)return;const it=byId(ed.id);S.ed=null;
if(it&&!it.f.trim()){if(it.o>=0){it.d=true;it.f=draft(it);}else S.items=S.items.filter(x=>x.id!==it.id);}
after();if(!silent){renderEdit();blur();}}
function cancelEdit(){
const ed=S.ed;if(!ed)return;const it=byId(ed.id);S.ed=null;
if(it){if(ed.isNew)S.items=S.items.filter(x=>x.id!==it.id);else it.f=ed.before;}
after();renderEdit();blur();}
function blur(){const a=document.activeElement;if(a&&a!==B&&a.blur)a.blur();}
function del(id){const it=byId(id);if(!it)return;if(S.ed&&S.ed.id===id)S.ed=null;
if(it.o>=0){it.d=true;it.f=draft(it);}else S.items=S.items.filter(x=>x.id!==id);after();renderEdit();}
function undel(id){const it=byId(id);if(!it)return;it.d=false;if(!it.f)it.f=draft(it);after();renderEdit();blur();}
function addAfter(aid){
if(S.ed){const k0=aid?S.items.findIndex(x=>x.id===aid):-1,pred=k0>0?S.items[k0-1].id:null;commitEdit(true);if(aid&&!byId(aid))aid=pred||'';}
let pos=0;if(aid){const k=S.items.findIndex(x=>x.id===aid);pos=k>=0?k+1:S.items.length;}
const it={id:newId(),o:-1,f:'',g:'\n\n',d:false};S.items.splice(pos,0,it);
if(pos>0&&S.items[pos-1].g.length<2)S.items[pos-1].g='\n\n';
S.ed={id:it.id,before:'',isNew:true,mode:'render'};renderEdit();
const e=host.querySelector('.rv-editing');if(e){e.querySelector('.rv-edta').focus({preventScroll:true});e.scrollIntoView({block:'nearest'});}}
function live(){return!B.dataset.rv||B.dataset.rv==='tensaku';}
host.addEventListener('click',e=>{
const act=e.target.closest('[data-act]');
if(act){const b=act.closest('.ms-blk'),id=b?b.dataset.id:null,a=act.dataset.act;
if(a==='commit')commitEdit();else if(a==='cancel')cancelEdit();else if(a==='delete')del(id);else if(a==='undelete')undel(id);else if(a==='addbelow')addAfter(id);return;}
const add=e.target.closest('.rv-addbtn');if(add){addAfter(add.dataset.after);return;}
const pv=e.target.closest('[data-mode]');if(pv){if(S.ed)S.ed.mode=pv.dataset.mode;refreshPreview();return;}
const b=e.target.closest('.ms-blk.rv-b');
if(!b||!live()||b.classList.contains('rv-editing')||b.classList.contains('rv-delrow'))return;
const s=getSelection();if(s&&!s.isCollapsed)return;
openEdit(b.dataset.id);});
host.addEventListener('keydown',e=>{
if(e.key!=='Enter'||!live()||!e.target.classList||!e.target.classList.contains('rv-b'))return;
if(e.target.classList.contains('rv-editing')||e.target.classList.contains('rv-delrow'))return;
e.preventDefault();openEdit(e.target.dataset.id);});
const pf=mk('div','rv-panel'),pd=mk('div','rv-panel'),ps=mk('div','rv-panel');
[pf,pd,ps].forEach(p=>{p.hidden=true;});
const fh=mk('div','rv-finhead'),fa=btn('rv-sm','直した後',()=>{S.draft=false;renderFinal();}),fb=btn('rv-sm','元の下書き',()=>{S.draft=true;renderFinal();}),fl=mk('span','rv-hint'),fart=mk('div','ms');
fart.dataset.prose='raw';fh.append(fa,fb,fl);pf.append(fh,fart);
const dnote=mk('p','rv-note','取り消し線は消した所、下線は足した所です。直した塊だけの一覧（押すとその場所へ移ります）：'),dlist=mk('div','rv-dlist'),dart=mk('div','ms');
dart.dataset.prose='raw';pd.append(dnote,dlist,dart);
const sta=mk('textarea','rv-ta rv-srcall'),sst=mk('p','rv-st'),srow=mk('div','rv-row');
sta.spellcheck=false;sta.setAttribute('aria-label','原稿全体の Markdown');
srow.append(btn('rv-main','反映（ブロックの分け方を合わせ直す）',applySource),btn('','取消（いまの状態に戻す）',()=>{refreshSrc(true);sst.textContent='いまの状態に戻しました。';}));
ps.append(mk('p','rv-note','原稿全体の Markdown を1つの欄で直せます。「反映」を押すと、元の原稿のブロックと突き合わせ直します（Ctrl+Enter でも反映）。'),sta,srow,sst);
host.after(pf,pd,ps);
const tb=mk('div','rv-tabs');tb.setAttribute('role','tablist');tb.setAttribute('aria-label','添削の画面');
const TABS=[['edit','直す'],['final','完成形'],['diff','差分'],['src','ソース全体']];
TABS.forEach(([k,l])=>{const b=btn('rv-tab',l,()=>setTab(k));b.setAttribute('role','tab');b.dataset.tab=k;tb.appendChild(b);});
tb.append(mk('span','rv-sp'),btn('rv-sm','下書きに戻す',resetAll));
host.before(tb);
function renderFinal(){
fart.innerHTML=docHtml(S.draft?O.head+O.items.map(x=>x.md+x.gap).join(''):finalMd());
fa.setAttribute('aria-pressed',!S.draft);fb.setAttribute('aria-pressed',S.draft);
fl.textContent=S.draft?'元の原稿（直す前）':'直した後の原稿（通読用）';}
function renderDiff(){
const list=[],parts=[];
S.items.forEach(it=>{const n=chg(it),ty=typeOf(it);
if(n){const hs=nonEq(segsFor(it));
list.push([it.id,lab(it)+'・直された '+n+' 文字',it.d?'ブロックごと削除':it.o<0?'ブロックを追加':hs.slice(0,4).map(blockText).join(' / ')+(hs.length>4?' / …':'')]);}
if(ty==='comment')return;
if(!n){parts.push('<div class="ms-blk rv-dblk" id="rv-d-'+it.id+'">'+safe(it.f)+'</div>');return;}
const html=it.d?safe(D0+draft(it)+D1):it.o<0?safe(I0+it.f+I1):diffRender(it).html;
parts.push('<div class="ms-blk rv-dblk rv-chg" data-id="'+it.id+'" id="rv-d-'+it.id+'"><span class="rv-dtag">'+esc(lt(it))+'・直された '+n+' 文字'+(it.d?'・削除':'')+'</span>'+html+'</div>');});
dlist.textContent='';
if(!list.length)dlist.appendChild(mk('span','rv-hint','まだ直した所はありません。'));
list.forEach(r=>{const d=mk('div','rv-ditem'),b=btn('rv-link',r[1],()=>{const e=$('rv-d-'+r[0]);if(e)e.scrollIntoView({block:'start'});});d.append(b,mk('span','rv-chgtxt',' '+r[2]));dlist.appendChild(d);});
dart.innerHTML=parts.join('');marks(dart,'.rv-dblk.rv-chg');}
function refreshSrc(force){if(S.dirty&&!force)return;sta.value=finalMd();S.dirty=false;}
const lcs=(A,Bx,eq)=>{
const n=A.length,m=Bx.length,dp=[];for(let i=0;i<=n;i++)dp.push(new Uint16Array(m+1));
for(let i=n-1;i>=0;i--)for(let j=m-1;j>=0;j--)dp[i][j]=eq(A[i],Bx[j])?dp[i+1][j+1]+1:Math.max(dp[i+1][j],dp[i][j+1]);
const ps2=[];let i=0,j=0;
while(i<n&&j<m){if(eq(A[i],Bx[j])){ps2.push([i,j]);i++;j++;}else if(dp[i+1][j]>=dp[i][j+1])i++;else j++;}
return ps2;};
const bgc=new Map();
function bg(s){let m=bgc.get(s);if(!m){m=new Map();const t=s.length>4000?s.slice(0,4000):s;for(let i=0;i+1<t.length;i++){const g=t.slice(i,i+2);m.set(g,(m.get(g)||0)+1);}bgc.set(s,m);}return m;}
function sim(a,b){if(a===b)return 1;const A=bg(a),Bx=bg(b);let it=0,na=0,nb=0;A.forEach((v,k)=>{na+=v;if(Bx.has(k))it+=Math.min(v,Bx.get(k));});Bx.forEach(v=>{nb+=v;});return na+nb?(2*it)/(na+nb):0;}
function realign(P){
const N=P.items,vis2=S.items.filter(it=>!it.d),A=vis2.map(it=>it.f),Bx=N.map(b=>b.md);
const exact=lcs(A,Bx,(a,b)=>a===b),result=[];let pi=0,pj=0;
exact.concat([[A.length,Bx.length]]).forEach(([ai,aj])=>{
const ra=[],rb=[];for(let x=pi;x<ai;x++)ra.push(x);for(let y=pj;y<aj;y++)rb.push(y);
if(ra.length&&rb.length){const sub=lcs(ra.map(x=>A[x]),rb.map(y=>Bx[y]),(a,b)=>sim(a,b)>=0.5);let x=0,y=0;
sub.concat([[ra.length,rb.length]]).forEach(([si,sj])=>{while(x<si)result.push([ra[x++],-1]);while(y<sj)result.push([-1,rb[y++]]);if(si<ra.length){result.push([ra[si],rb[sj]]);x=si+1;y=sj+1;}});}
else{ra.forEach(x=>result.push([x,-1]));rb.forEach(y=>result.push([-1,y]));}
if(ai<A.length)result.push([ai,aj]);
pi=ai+1;pj=aj+1;});
const cnt={changed:0,added:0,deleted:0},ni=[];
result.forEach(([i,j])=>{
if(i>=0&&j>=0){const it=vis2[i];if(it.f!==Bx[j])cnt.changed++;it.f=Bx[j];it.g=N[j].gap;ni.push(it);}
else if(i>=0){const it=vis2[i];cnt.deleted++;if(it.o>=0){it.d=true;it.f=draft(it);ni.push(it);}}
else{ni.push({id:newId(),o:-1,f:Bx[j],g:N[j].gap,d:false});cnt.added++;}});
S.items.forEach((it,idx)=>{if(!it.d||ni.indexOf(it)>=0)return;
let pred=null;for(let k=idx-1;k>=0;k--){if(!S.items[k].d){pred=S.items[k].id;break;}}
let at=0;if(pred){const p=ni.findIndex(x=>x.id===pred);at=p>=0?p+1:0;}
ni.splice(at,0,it);});
S.items=ni;S.head=P.head;return cnt;}
function applySource(){
if(S.ed)commitEdit(true);
const r=realign(parseBlocks(sta.value.replace(/\r\n?/g,'\n')));S.dirty=false;after();renderEdit();sta.value=finalMd();
sst.textContent='反映しました。変更 '+r.changed+'・追加 '+r.added+'・削除 '+r.deleted+' ブロック（差分はブロックごとに取り直しました）。';}
sta.addEventListener('input',()=>{S.dirty=true;sst.textContent='未反映の変更があります。「反映」を押すとブロックの分け方を合わせ直します。';});
sta.addEventListener('keydown',e=>{if(e.key==='Enter'&&(e.metaKey||e.ctrlKey)){e.preventDefault();applySource();}});
const cb=btn('','',()=>{setTab('diff');tb.scrollIntoView({block:'start'});},'rv-t-count');cb.hidden=true;put(cb);
function after(){
cb.textContent='直し '+count()+' 件';cb.hidden=!count();vis();
save();
if(S.tab==='diff')renderDiff();if(S.tab==='final')renderFinal();
R.rebuild();}
function setTab(k){
if(S.ed)commitEdit(true);
S.tab=k;
tb.querySelectorAll('.rv-tab').forEach(b=>b.setAttribute('aria-selected',b.dataset.tab===k));
host.hidden=k!=='edit';pf.hidden=k!=='final';pd.hidden=k!=='diff';ps.hidden=k!=='src';
if(k==='edit')renderEdit();if(k==='diff')renderDiff();if(k==='final')renderFinal();if(k==='src')refreshSrc(false);}
function resetAll(){
if(!window.confirm('原稿を元の状態に戻します。書き換え・追加・削除は全部消えます。よろしいですか。'))return;
reset();}
function reset(){S.items=fresh();S.head=O.head;S.nn=1;S.ed=null;S.draft=false;S.dirty=false;cache.clear();sst.textContent='';setTab(S.tab);if(S.tab==='src')refreshSrc(true);after();wr(KEY,null);}
function lines(){
const out=[],fp=new Map();S.items.filter(x=>!x.d).forEach((x,k)=>fp.set(x.id,k+1));
S.items.forEach(it=>{const n=chg(it);if(!n)return;
if(it.d)out.push('- 段落 '+(it.o+1)+': (削除)');
else if(it.o<0)out.push('- 段落 '+fp.get(it.id)+': (追加) '+qt(it.f));
else out.push('- 段落 '+(it.o+1)+': '+pairs(segsFor(it)).join(' / '));});
if(!out.length)return['- 変更なし'];
const md=finalMd().replace(/\s+$/,''),f=md.indexOf('```')>=0?'````':'```';
out.push(f+'markdown');md.split('\n').forEach(l=>out.push(l));out.push(f);return out;}
R.extras.push({role:'tensaku',lines:lines,forget:reset});
setTab('edit');after();
}
"""

_TENSAKU_PAGE_JS = r"""function pageMode(){
const KEY='uc-tensaku:'+document.title+':page';
let P=rd(KEY);if(!P||!P.e||!P.a||!P.g||typeof P.e!=='object'||typeof P.a!=='object'||typeof P.g!=='object')P={e:{},a:{},g:{}};
const unit=n=>document.querySelector('[data-blk="'+n+'"]');
Object.keys(P.e).forEach(k=>{const v=P.e[k];if(!unit(k)||P.g[k]!==sig(unit(k))||!v||(!v.d&&typeof v.t!=='string'))delete P.e[k];});
Object.keys(P.a).forEach(k=>{if(!unit(k)||P.g[k]!==sig(unit(k))||!Array.isArray(P.a[k]))delete P.a[k];else P.a[k]=P.a[k].filter(x=>typeof x==='string'&&x);if(P.a[k]&&!P.a[k].length)delete P.a[k];});
const orig={},base=n=>{if(!(n in orig)){const u=unit(n);orig[n]=u?txt(u):'';}return orig[n];};
const on=()=>B.dataset.rv==='tensaku';
let ed=null;
const fit=a=>{a.style.height='auto';a.style.height=Math.min(a.scrollHeight+2,Math.round(innerHeight*0.6))+'px';};
const n0=()=>Object.keys(P.e).length+Object.keys(P.a).reduce((s,k)=>s+P.a[k].filter(Boolean).length,0);
function wrapOf(n,make){const u=unit(n);if(!u)return null;let w=u.nextElementSibling;if(w&&w.classList.contains('rv-x'))return w;if(!make)return null;
const tr=u.tagName==='TR';w=mk(tr?'tr':'div','rv-x rv-ui');if(tr){const td=mk('td');td.colSpan=100;w.appendChild(td);}u.after(w);return w;}
const inner=w=>w.tagName==='TR'?w.firstChild:w;
function row2(badge,tone,body,ops){const d=mk('div','rv-sumrow'),b=mk('span','rv-badge'+(tone?' rv-on':''),badge),t=mk('span','rv-difftxt');
if(typeof body==='string')t.innerHTML=body;d.append(b,t);ops.forEach(o=>d.appendChild(btn('rv-sm',o[0],o[1])));return d;}
function paint(n){
const u=unit(n);if(!u)return;
const e=P.e[n],ad=P.a[n]||[],open=ed&&ed.n===n;
if(e&&e.d)u.setAttribute('data-rv-t','d');else if(e)u.setAttribute('data-rv-t','c');else u.removeAttribute('data-rv-t');
let w=wrapOf(n,false);
if(!e&&!ad.length&&!open){if(w)w.remove();return;}
w=w||wrapOf(n,true);const c=inner(w);c.textContent='';
if(open&&ed.k==='u')c.appendChild(ed.el);
else if(e)c.appendChild(e.d?row2('削除',1,'<del>'+esc(cut(base(n),80))+'</del>',[['元に戻す',()=>{delete P.e[n];changed(n);}]]):row2('直し',1,segHtml(diffWords(base(n),e.t)),[['直す',()=>openU(n)],['元に戻す',()=>{delete P.e[n];changed(n);}]]));
ad.forEach((x,i)=>{c.appendChild(open&&ed.k==='a'&&ed.i===i?ed.el:row2('追加',1,esc(x),[['直す',()=>openA(n,i,false)],['削除',()=>{P.a[n].splice(i,1);if(!P.a[n].length)delete P.a[n];changed(n);}]]));});}
function changed(n){const u=unit(n);if(u&&(P.e[n]||P.a[n]))P.g[n]=sig(u);paint(n);cnt.textContent='直し '+n0()+' 件';cnt.hidden=!n0();vis();items();wr(KEY,n0()?P:null);R.rebuild();}
function box(title,init,diffBase,extra){
const el=mk('div','rv-ed'),ta=mk('textarea','rv-ta'),dv=mk('div','rv-diff'),row=mk('div','rv-row');
el.appendChild(mk('p','rv-edh',title));ta.value=init;ta.setAttribute('aria-label',title);ta.rows=3;el.appendChild(ta);
const upd=()=>{if(diffBase!=null)dv.innerHTML=segHtml(diffWords(diffBase,ta.value));fit(ta);};
if(diffBase!=null)el.appendChild(dv);
ta.addEventListener('input',upd);
ta.addEventListener('keydown',e=>{if(e.key==='Enter'&&(e.metaKey||e.ctrlKey)){e.preventDefault();closeEd(true);}});
row.append(btn('rv-main','確定',()=>closeEd(true)),btn('','取消',()=>closeEd(false)),mk('span','rv-sp'));
(extra||[]).forEach(o=>row.appendChild(btn(o[2]||'',o[0],o[1])));el.appendChild(row);
return{el:el,ta:ta,upd:upd};}
function openU(n){
closeEd(true);if(!unit(n))return;const e=P.e[n];
const b=box('#'+n+' を直す（書き換えると、差分が下に出ます）',e&&!e.d&&e.t!=null?e.t:base(n),base(n),[['＋ この後に段落を足す',()=>addTo(n)],['削除',()=>{ed=null;P.e[n]={d:1};changed(n);},'rv-danger']]);
ed={k:'u',n:n,el:b.el,ta:b.ta};paint(n);b.upd();b.ta.focus();}
function openA(n,i,fresh){
closeEd(true);if(!unit(n))return;
const b=box('#'+n+' の後に足す段落',(P.a[n]||[])[i]||'',null);
ed={k:'a',n:n,i:i,fresh:fresh,el:b.el,ta:b.ta};paint(n);b.upd();b.ta.focus();}
function addTo(n){closeEd(true);const a=P.a[n]||(P.a[n]=[]);a.push('');openA(n,a.length-1,true);}
function closeEd(ok){
if(!ed)return;const d=ed,v=d.ta.value.trim();ed=null;
if(d.k==='u'){if(ok){if(!v)P.e[d.n]={d:1};else if(v.replace(/\s+/g,' ')===base(d.n))delete P.e[d.n];else P.e[d.n]={t:v};}}
else{const a=P.a[d.n]||(P.a[d.n]=[]);if(ok&&v)a[d.i]=v;else if(ok||d.fresh)a.splice(d.i,1);if(!a.length)delete P.a[d.n];}
changed(d.n);}
const dr=mk('div','rv-ui rv-drawer'),dh=mk('div','rv-dhead'),list=mk('div','rv-dbody');
dr.hidden=true;dr.setAttribute('role','dialog');dr.setAttribute('aria-label','直しの一覧');
dh.append(mk('b','','直しの一覧'),mk('span','rv-sp'),btn('','閉じる',closeDrawer));dr.append(dh,list);dfoot(dr,closeDrawer);
function openDrawer(){document.dispatchEvent(new CustomEvent('rv:drawer',{detail:'t'}));items();dr.hidden=false;}
function closeDrawer(){dr.hidden=true;}
document.addEventListener('rv:drawer',e=>{if(e.detail!=='t')closeDrawer();});
const keys=()=>Object.keys(P.e).concat(Object.keys(P.a)).map(Number).filter((n,i,a)=>a.indexOf(n)===i).sort((a,b)=>a-b);
function items(){list.textContent='';
if(!n0()){list.appendChild(mk('p','rv-empty','まだ直した所はありません。「直す」を押してから、本文の塊を押してください。'));return;}
keys().forEach(n=>{const e=P.e[n],u=unit(n),go=()=>{closeDrawer();if(u)u.scrollIntoView({behavior:'smooth',block:'center'});};
if(e){const d=mk('div','rv-item'),o=mk('div','rv-ops'),t=mk('p','rv-n');t.innerHTML=e.d?'<del>'+esc(cut(base(n),80))+'</del>':segHtml(diffWords(base(n),e.t));
d.append(mk('p','rv-q','#'+n+(e.d?' 削除':' 直し')),t);
o.append(btn('rv-link','該当箇所へ',go),btn('rv-link','元に戻す',()=>{delete P.e[n];changed(n);}));d.appendChild(o);list.appendChild(d);}
(P.a[n]||[]).forEach((x,i)=>{const d=mk('div','rv-item'),o=mk('div','rv-ops');d.append(mk('p','rv-q','#'+n+' の後に追加'),mk('p','rv-n',x));
o.append(btn('rv-link','該当箇所へ',go),btn('rv-link','削除',()=>{P.a[n].splice(i,1);if(!P.a[n].length)delete P.a[n];changed(n);}));d.appendChild(o);list.appendChild(d);});});}
const tog=btn('','直す',()=>setRv('tensaku'),'rv-tensaku'),cnt=btn('','',openDrawer,'rv-t-count');
tog.setAttribute('aria-pressed','false');cnt.hidden=true;put(tog);put(cnt);
function lines(){const out=[];
keys().forEach(n=>{const e=P.e[n];
if(e)out.push('- 段落 '+n+': '+(e.d?'(削除)':pairs(diffWords(base(n),e.t)).join(' / ')));
(P.a[n]||[]).filter(Boolean).forEach(x=>out.push('- 段落 '+n+' の後: (追加) '+qt(x)));});
if(out.length)out.push('（説明の頁の添削＝完成形は無し。#N は文字だけの版の行の番号）');return out;}
function forget(){ed=null;P={e:{},a:{},g:{}};document.querySelectorAll('.rv-x').forEach(w=>w.remove());
document.querySelectorAll('[data-rv-t]').forEach(u=>u.removeAttribute('data-rv-t'));
cnt.textContent='直し 0 件';cnt.hidden=true;vis();items();wr(KEY,null);R.rebuild();}
R.extras.push({role:'tensaku',lines:lines,forget:forget});
function sync(){const o=on();B.classList.toggle('rv-t',o);tog.setAttribute('aria-pressed',o);tabs();if(!o)closeEd(true);}
document.addEventListener('rv:mode',sync);
document.addEventListener('click',e=>{
if(!on()||e.defaultPrevented)return;const g=e.target;
if(!g.closest||g.closest('.rv-ui,a,button,summary,input,textarea,label,select'))return;
const s=getSelection();if(s&&!s.isCollapsed)return;
const u=g.closest('[data-blk]');if(u)openU(+u.dataset.blk);});
document.addEventListener('keydown',e=>{
if(e.key==='Escape'){if(outOpen())return;if(ed)closeEd(false);else if(!dr.hidden)closeDrawer();else if(on())setRv('tensaku');return;}
if(!on()||(e.key!=='Enter'&&e.key!==' '))return;
const u=e.target;if(u&&u.matches&&u.matches('[data-blk]')){e.preventDefault();openU(+u.dataset.blk);}});
B.appendChild(dr);
keys().forEach(paint);
cnt.textContent='直し '+n0()+' 件';cnt.hidden=!n0();vis();R.rebuild();sync();
}
"""

_TENSAKU_TAIL_JS = "msMode?manuscript():pageMode();\ncomposeUI();\n"

SHITEKI_SCRIPT = _wrap(_KIT_JS + _SHITEKI_JS).replace("__CHIPS__", _chips_js())

TENSAKU_SCRIPT = _wrap(
    _KIT_JS + _TENSAKU_CORE_JS + _TENSAKU_MD_JS + _TENSAKU_MS_JS + _TENSAKU_PAGE_JS + _TENSAKU_TAIL_JS
)

ROLE_SCRIPTS = {"shiteki": SHITEKI_SCRIPT, "tensaku": TENSAKU_SCRIPT}

_CSS_COMMON = r""".rv-ui[hidden],.rv-btn[hidden],#rv-bar[hidden]{display:none!important}
#rv-bar{position:fixed;right:.75rem;bottom:.75rem;z-index:1200;display:flex;flex-wrap:wrap;gap:.35rem;justify-content:flex-end;max-width:calc(100vw - 1.5rem);box-sizing:border-box;padding:.35rem;background:var(--surface);border:1px solid var(--rule);border-radius:2px;box-shadow:0 4px 18px color-mix(in srgb,var(--ink) 22%,transparent)}
.rv-btn{min-height:2.3rem;padding:.3rem .8rem;border:1px solid var(--rule);border-radius:2px;background:var(--surface);color:var(--ink);font-family:inherit;font-size:.82rem;font-weight:700;line-height:1.4;cursor:pointer}
.rv-btn:hover{background:var(--surface-2);color:var(--ink)}
.rv-btn:focus-visible{outline:3px solid color-mix(in srgb,var(--accent) 48%,transparent);outline-offset:2px}
.rv-btn.rv-main,.rv-btn.rv-main:hover{background:var(--accent);border-color:var(--accent);color:var(--on-accent)}
.rv-btn.rv-danger{color:var(--fail);border-color:var(--fail)}
.rv-btn.rv-sm{min-height:1.8rem;padding:.1rem .6rem;font-size:.74rem}
.rv-btn.rv-link,.rv-btn.rv-link:hover{min-height:0;padding:0;border:0;background:none;color:var(--accent);font-size:.78rem}
.rv-sp{flex:1}
.rv-row{display:flex;flex-wrap:wrap;gap:.5rem;align-items:center;margin-top:.6rem}
.rv-ta{display:block;width:100%;box-sizing:border-box;min-height:4rem;padding:.5rem .65rem;border:1px solid var(--rule);border-radius:2px;background:var(--surface);color:var(--ink);font:inherit;font-size:1rem;line-height:1.7;resize:vertical}
.rv-ta:focus{outline:2px solid var(--fail);outline-offset:0}
.rv-st{margin:0 0 .5rem;font-size:.82rem;color:var(--ink-2)}
.rv-out{position:fixed;left:50%;bottom:0;transform:translateX(-50%);z-index:1350;width:min(46rem,100%);box-sizing:border-box;padding:.9rem 1rem calc(.9rem + env(safe-area-inset-bottom));background:var(--surface);border:1px solid var(--rule);border-bottom:0;border-radius:4px 4px 0 0;box-shadow:0 -6px 24px color-mix(in srgb,var(--ink) 25%,transparent)}
.rv-out textarea{display:block;width:100%;box-sizing:border-box;height:36vh;padding:.5rem;border:2px solid var(--fail);border-radius:2px;background:var(--surface-2);color:var(--ink);font:.78rem/1.5 "IBM Plex Mono",ui-monospace,monospace;resize:vertical}
.rv-drawer{position:fixed;top:0;right:0;bottom:0;z-index:1300;display:flex;flex-direction:column;width:min(26rem,100%);box-sizing:border-box;background:var(--surface);border-left:1px solid var(--rule);box-shadow:-6px 0 24px color-mix(in srgb,var(--ink) 22%,transparent)}
.rv-dhead{display:flex;align-items:center;gap:.5rem;padding:.7rem .9rem;border-bottom:1px solid var(--rule);font-weight:700}
.rv-dbody{flex:1;overflow:auto;padding:.7rem .9rem}
.rv-item{margin-bottom:.55rem;padding:.55rem .7rem;border:1px solid var(--rule);border-left:3px solid var(--fail);border-radius:2px;background:var(--surface);font-size:.86rem}
.rv-q{margin:0 0 .15rem;overflow:hidden;color:var(--ink-2);font-size:.78rem;text-overflow:ellipsis;white-space:nowrap}
.rv-n{margin:0;font-size:.88rem;overflow-wrap:anywhere;white-space:pre-wrap}
.rv-ops{display:flex;gap:.8rem;margin-top:.3rem}
.rv-dfoot{padding:.7rem .9rem;border-top:1px solid var(--rule)}
.rv-empty{color:var(--ink-2);font-size:.86rem}
@media(max-width:600px){#rv-bar{left:.5rem;right:.5rem;bottom:.5rem}#rv-bar .rv-btn{flex:1 1 auto}}
@media print{#rv-bar,.rv-shade,.rv-sheet,.rv-drawer,.rv-out,.rv-sel,.rv-x,.rv-tabs{display:none!important}[data-rv-p]::after{display:none!important}[data-rv-s],[data-rv-t]{box-shadow:none!important}}
"""

_CSS_SHITEKI = r""".rv-shade{position:fixed;inset:0;z-index:1250;background:color-mix(in srgb,var(--ink) 40%,transparent)}
.rv-sheet{position:fixed;left:50%;bottom:0;transform:translateX(-50%);z-index:1300;width:min(44rem,100%);max-height:90vh;overflow:auto;box-sizing:border-box;padding:.9rem 1rem calc(.9rem + env(safe-area-inset-bottom));background:var(--surface);border:1px solid var(--rule);border-bottom:0;border-radius:4px 4px 0 0;box-shadow:0 -6px 24px color-mix(in srgb,var(--ink) 25%,transparent)}
.rv-target{margin:0 0 .5rem;max-height:3.4em;overflow:hidden;color:var(--ink-2);font-size:.82rem}
.rv-target b{color:var(--fail)}
.rv-chips{display:flex;flex-wrap:wrap;gap:.35rem;margin-bottom:.55rem}
.rv-chip{min-height:2rem;border-radius:999px;font-size:.8rem}
.rv-chip.on,.rv-chip.on:hover{background:var(--fail);border-color:var(--fail);color:var(--on-accent)}
#rv-shiteki[aria-pressed="true"],#rv-shiteki[aria-pressed="true"]:hover{background:var(--fail);border-color:var(--fail);color:var(--on-accent)}
.rv-msg{margin:.4rem 0 0;color:var(--fail);font-size:.82rem}
.rv-msg:empty{display:none}
.rv-sel{position:absolute;z-index:1300;padding:.3rem .8rem;border:0;border-radius:2px;background:var(--fail);color:var(--on-accent);font-family:inherit;font-size:.82rem;font-weight:700;cursor:pointer;box-shadow:0 2px 8px color-mix(in srgb,var(--ink) 30%,transparent)}
.rv-chipname{margin-right:.4rem;color:var(--fail);font-weight:700}
.rv-s [data-blk]:not(tr){position:relative;cursor:pointer}
.rv-s [data-blk]{cursor:pointer}
.rv-s [data-blk]:hover{outline:1.5px dashed color-mix(in srgb,var(--fail) 70%,transparent);outline-offset:3px}
.rv-s [data-blk]:focus-visible{outline:2px solid var(--fail);outline-offset:3px}
.rv-s [data-blk]:not(tr):not([data-rv-p]):hover::after{content:"#" attr(data-blk);position:absolute;top:.25rem;right:.35rem;z-index:2;padding:0 .35rem;border:1px solid var(--fail);border-radius:2px;background:var(--surface);color:var(--fail);font:600 .7rem/1.5 "IBM Plex Mono",ui-monospace,monospace;pointer-events:none}
[data-rv-s]{box-shadow:inset 3px 0 0 var(--fail)}
[data-rv-s][data-rv-s]{background-color:var(--fail-soft)}
tr[data-rv-s]{box-shadow:none;background-color:transparent}
tr[data-rv-s]>*{background-color:var(--fail-soft)}
tr[data-rv-s]>:first-child{box-shadow:inset 3px 0 0 var(--fail)}
[data-rv-p]{position:relative}
[data-rv-p]::after{content:attr(data-rv-p);position:absolute;top:.25rem;right:.35rem;z-index:2;min-width:1.4rem;box-sizing:border-box;padding:0 .4rem;border-radius:999px;background:var(--fail);color:var(--on-accent);font:700 .7rem/1.5 "IBM Plex Mono",ui-monospace,monospace;text-align:center;pointer-events:none}
"""

_CSS_TENSAKU = r"""#rv-tensaku[aria-pressed="true"],#rv-tensaku[aria-pressed="true"]:hover{background:var(--accent);border-color:var(--accent);color:var(--on-accent)}
.rv-btn.rv-on,.rv-btn.rv-on:hover{background:var(--accent-soft);border-color:var(--accent);color:var(--accent)}
.rv-t [data-blk]{cursor:pointer}
.rv-t [data-blk]:hover{outline:1.5px dashed color-mix(in srgb,var(--accent) 70%,transparent);outline-offset:3px}
.rv-t [data-blk]:focus-visible{outline:2px solid var(--accent);outline-offset:3px}
[data-rv-t]{box-shadow:inset -3px 0 0 var(--accent)}
[data-rv-s][data-rv-t]{box-shadow:inset 3px 0 0 var(--fail),inset -3px 0 0 var(--accent)}
[data-rv-t="d"]{opacity:.55;text-decoration:line-through}
tr[data-rv-t],tr[data-rv-s][data-rv-t]{box-shadow:none}
tr[data-rv-t]>:last-child{box-shadow:inset -3px 0 0 var(--accent)}
.rv-x{grid-column:1/-1;box-sizing:border-box;min-width:0;margin:.3rem 0}
.rv-ed{box-sizing:border-box;padding:.7rem .85rem;border:1.5px solid var(--accent);border-radius:2px;background:var(--surface);cursor:default}
.rv-edh{margin:0 0 .4rem;color:var(--ink-2);font-size:.8rem}
.rv-diff{margin-top:.5rem;padding:.4rem .6rem;border:1px dashed var(--rule);border-radius:2px;color:var(--ink);font-size:.88rem;overflow-wrap:anywhere;white-space:pre-wrap}
.rv-diff:empty{display:none}
.rv-diff del,.rv-difftxt del,.rv-n del,.ms del,.rv-raw del{color:var(--fail);text-decoration:line-through;text-decoration-thickness:1.5px}
.rv-diff ins,.rv-difftxt ins,.rv-n ins,.ms ins,.rv-raw ins{color:var(--fail);text-decoration:underline;text-decoration-thickness:1.5px;text-underline-offset:3px}
.rv-sumrow{display:flex;flex-wrap:wrap;gap:.5rem;align-items:baseline;padding:.4rem .6rem;border-left:3px solid var(--accent);background:var(--surface-2);font-size:.86rem}
.rv-sumrow+.rv-sumrow{margin-top:.3rem}
.rv-difftxt{flex:1;min-width:8rem;overflow-wrap:anywhere;white-space:pre-wrap}
.rv-badge{display:inline-block;padding:.05rem .4rem;border:1px solid var(--rule);border-radius:2px;color:var(--ink-2);font:600 .7rem/1.6 "IBM Plex Mono",ui-monospace,monospace;white-space:nowrap}
.rv-badge.rv-on{border-color:var(--fail);color:var(--fail)}
.rv-tabs{display:flex;flex-wrap:wrap;align-items:center;gap:.2rem;margin:.3rem 0 .6rem;border-bottom:1px solid var(--rule)}
.rv-tab,.rv-tab:hover{min-height:2.2rem;padding:.2rem .8rem;border:0;border-bottom:2px solid transparent;border-radius:0;background:none;color:var(--ink-2)}
.rv-tab:hover{background:var(--surface-2);color:var(--ink)}
.rv-tab[aria-selected="true"]{border-bottom-color:var(--accent);color:var(--accent)}
.rv-b{position:relative;border-radius:2px;cursor:pointer}
.rv-b:hover,.rv-b:focus-visible{outline:1px solid var(--rule);outline-offset:2px}
.rv-b:focus-visible{outline-color:var(--accent)}
.rv-pen{position:absolute;top:.2rem;right:.5rem;opacity:0;color:var(--accent);font:600 .7rem/1.4 "IBM Plex Mono",ui-monospace,monospace}
.rv-b:hover .rv-pen,.rv-b:focus-visible .rv-pen{opacity:1}
.rv-chg{padding-left:.7rem;box-shadow:inset 3px 0 0 var(--fail)}
.rv-tools{display:flex;flex-wrap:wrap;align-items:center;gap:.5rem;min-height:1.3rem;margin-bottom:.2rem;color:var(--ink-2);font:.72rem/1.6 "IBM Plex Mono",ui-monospace,monospace}
.rv-sum{flex:1 1 0;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.rv-snip{max-width:55%;overflow:hidden;color:var(--fail);text-decoration:line-through;text-overflow:ellipsis;white-space:nowrap}
.rv-delrow{cursor:default;box-shadow:inset 3px 0 0 var(--fail);padding:.3rem .7rem}
.rv-addstrip{display:flex;align-items:center;justify-content:center;height:1.4rem;margin:-.3rem 0}
.rv-addbtn{min-height:0;padding:0 .6rem;border:1px dashed var(--accent);border-radius:2px;background:var(--surface);color:var(--accent);font:600 .7rem/1.6 "IBM Plex Mono",ui-monospace,monospace;opacity:0;cursor:pointer}
.rv-addstrip:hover .rv-addbtn,.rv-addbtn:focus{opacity:1}
@media(hover:none){.rv-pen{opacity:.8}.rv-addbtn{opacity:.7}}
.rv-editing{box-sizing:border-box;margin:.4rem 0;padding:.7rem .85rem;border:1.5px solid var(--fail);background:var(--surface);cursor:default}
.rv-edhead{display:flex;flex-wrap:wrap;align-items:center;gap:.5rem;margin-bottom:.4rem;color:var(--ink-2);font:.72rem/1.6 "IBM Plex Mono",ui-monospace,monospace}
.rv-pair{display:grid;grid-template-columns:1fr 1fr;gap:.8rem;align-items:start}
.rv-srcbox,.rv-prevbox{min-width:0}
.rv-lbl{display:flex;flex-wrap:wrap;gap:.3rem;align-items:center;min-height:1.6rem;margin:0 0 .3rem;color:var(--ink-2);font-size:.74rem}
.rv-prev{min-height:5rem;padding:.5rem .7rem;border:1px dashed var(--rule);border-radius:2px;overflow-wrap:anywhere}
.rv-warn{margin:.3rem 0 0;color:var(--warn);font-size:.8rem}
.rv-warn:empty{display:none}
.rv-edta{font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.92rem}
.rv-hint{color:var(--ink-2);font-size:.76rem}
.rv-note{margin:.2rem 0 .5rem;color:var(--ink-2);font-size:.82rem}
.rv-panel{margin-top:.4rem}
.rv-finhead{display:flex;flex-wrap:wrap;gap:.4rem;align-items:center;margin-bottom:.6rem}
.rv-finhead .rv-btn[aria-pressed="true"]{background:var(--accent);border-color:var(--accent);color:var(--on-accent)}
.rv-dlist{margin:.4rem 0 1rem;padding:.5rem .8rem;border:1px solid var(--rule);border-radius:2px}
.rv-ditem{margin:.2rem 0;font-size:.86rem}
.rv-chgtxt{color:var(--fail)}
.rv-dblk.rv-chg{scroll-margin-top:1rem}
.rv-dtag{display:block;color:var(--fail);font:.7rem/1.6 "IBM Plex Mono",ui-monospace,monospace}
.rv-srcall{min-height:60vh;font-family:"IBM Plex Mono",ui-monospace,monospace;font-size:.9rem}
.rv-raw{margin:.3rem 0;color:var(--ink-2);font:.75rem/1.6 "IBM Plex Mono",ui-monospace,monospace;overflow-wrap:anywhere;white-space:pre-wrap}
.rv-raw span.rv-ctx,.rv-ctx{opacity:.7}
.rv-ph{color:var(--ink-2);font-size:.85rem}
@media(max-width:700px){.rv-pair{grid-template-columns:1fr}}
.ms[hidden],.ms-blk[hidden],.rv-panel[hidden],.rv-tabs[hidden]{display:none!important}
"""

REVIEW_CSS_SHITEKI = _CSS_COMMON + _CSS_SHITEKI

REVIEW_CSS_TENSAKU = _CSS_COMMON + _CSS_TENSAKU

_ROLE_CSS = {"shiteki": _CSS_SHITEKI, "tensaku": _CSS_TENSAKU}


def review_css(roles: Sequence[str]) -> str:
    """使う役割（"shiteki"・"tensaku"）に合わせた CSS。共通の部分は1回だけ入れる。"""
    chosen = [role for role in ROLE_ORDER if role in roles and role in _ROLE_CSS]
    if not chosen:
        return ""
    return _CSS_COMMON + "".join(_ROLE_CSS[role] for role in chosen)
