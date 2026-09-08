/* ============================================================
   student-submit.js — 學習單識別列＋繳交模組（自足、無建置、可重用）
   規格權威來源：引導規範/學習單資料與提交規範.md（識別欄／題型標註／資料契約）

   用法：頁面尾端放
     <script src="student-submit.js"></script>
     <script>
       StudentSubmit.init({
         worksheetId: 'g5-L02',
         title: '事實與意見區分',
         lessonPath: 'g5/L02',
         firebaseConfig: {...},          // 頁面已 init 過 Firebase 可省略
         collect: function(){ return {answers:{...}, qtypes:{...}} },  // 選填：不給就自動掃 [data-qid][data-qtype]
         mount: '#submitHere'            // 選填：繳交鈕掛載處；不給就 append 到 <body> 尾
       });
       // 選用：開放題即時同儕動態（留言牆）
       StudentSubmit.liveFeed({ worksheetId:'g5-L02', qid:'essay', mount:'#feedHere', tag:'班級標籤(選填)' });
     </script>

   識別列：年級/班級/學號，一律數字，自動注入頁面最上方（<body> 第一個子節點前），存 localStorage。
   繳交資料：submissions/{worksheetId}__{grade}-{className}-{studentId}
     { worksheetId, worksheetTitle, lessonPath, grade, className, studentId,
       answers, qtypes, scoreAnswers, experienceAnswers, openAnswers,
       accuracyRate, experienceCompletion, status:'submitted', submittedAt }
   ============================================================ */
(function (global) {
  var CDN = 'https://www.gstatic.com/firebasejs/10.8.0/';
  function loadScript(src){return new Promise(function(res,rej){var s=document.createElement('script');s.src=src;s.onload=res;s.onerror=rej;document.head.appendChild(s);});}
  var _fbReady=null;
  function ensureFirebase(cfg){
    if (global.firebase && global.firebase.apps && global.firebase.apps.length) return Promise.resolve();
    if (_fbReady) return _fbReady;   // 避免 init()＋liveFeed() 同時呼叫造成重複載入 script
    _fbReady = loadScript(CDN+'firebase-app-compat.js')
      .then(function(){return loadScript(CDN+'firebase-auth-compat.js');})
      .then(function(){return loadScript(CDN+'firebase-firestore-compat.js');})
      .then(function(){ if(!global.firebase.apps.length) global.firebase.initializeApp(cfg); });
    return _fbReady;
  }
  function ensureAuth(auth){
    return auth.currentUser ? Promise.resolve(auth.currentUser) : auth.signInAnonymously().then(function(cred){return cred.user;});
  }
  function digits(s){return String(s||'').replace(/[^0-9]/g,'');}
  function norm(v){if(Array.isArray(v))return v.map(norm).sort().join('、');return String(v==null?'':v).trim().toLowerCase();}

  // ===== 識別列（年級/班級/學號，數字限制，localStorage 持久化）=====
  var ID_KEY='wk_identity';
  function loadIdentity(){try{return JSON.parse(localStorage.getItem(ID_KEY)||'{}');}catch(e){return {};}}
  function saveIdentity(o){try{localStorage.setItem(ID_KEY,JSON.stringify(o));}catch(e){}}
  function getIdentity(){
    var g=digits(document.getElementById('wkGrade')&&document.getElementById('wkGrade').value);
    var c=digits(document.getElementById('wkClass')&&document.getElementById('wkClass').value);
    var s=digits(document.getElementById('wkStudentId')&&document.getElementById('wkStudentId').value);
    return {grade:g?Number(g):null, className:c?Number(c):null, studentId:s?Number(s):null};
  }
  function identityValid(id){return id.grade!=null && id.className!=null && id.studentId!=null;}

  var ID_CSS = ''
    + '.wkid{position:sticky;top:0;z-index:40;background:#fff;border-bottom:2px solid #c7d2fe;padding:8px 14px;display:flex;gap:10px;align-items:center;flex-wrap:wrap;font-family:inherit}'
    + '.wkid b{font-size:13px;color:#3730a3;white-space:nowrap}'
    + '.wkid input{width:56px;font:inherit;font-size:14px;padding:6px 8px;border:1px solid #cbd5e1;border-radius:7px;outline:none;text-align:center}'
    + '.wkid input:focus{border-color:#6366f1;box-shadow:0 0 0 3px #e0e7ff}'
    + '.wkid label{font-size:11px;color:#64748b;display:flex;flex-direction:column;gap:2px;align-items:center}'
    + '.wkid .ok{font-size:11px;font-weight:700;color:#15803d}';

  function injectIdentityBar(){
    if(document.getElementById('wkIdentityBar'))return;
    var style=document.createElement('style');style.textContent=ID_CSS;document.head.appendChild(style);
    var saved=loadIdentity();
    var bar=document.createElement('div');bar.id='wkIdentityBar';bar.className='wkid';
    bar.innerHTML='<b>我是誰</b>'
      +'<label>年級<input id="wkGrade" inputmode="numeric" maxlength="2" value="'+(saved.grade||'')+'"></label>'
      +'<label>班級<input id="wkClass" inputmode="numeric" maxlength="2" value="'+(saved.className||'')+'"></label>'
      +'<label>學號<input id="wkStudentId" inputmode="numeric" maxlength="2" value="'+(saved.studentId||'')+'"></label>'
      +'<span class="ok" id="wkIdOk" style="display:none">已記住</span>';
    document.body.insertBefore(bar, document.body.firstChild);
    ['wkGrade','wkClass','wkStudentId'].forEach(function(id){
      var el=document.getElementById(id);
      el.addEventListener('input',function(){
        var d=digits(el.value); if(d!==el.value)el.value=d;
        var idn=getIdentity();
        if(identityValid(idn)){saveIdentity(idn);document.getElementById('wkIdOk').style.display='';}
        else document.getElementById('wkIdOk').style.display='none';
      });
    });
    if(identityValid(saved))document.getElementById('wkIdOk').style.display='';
  }

  // ===== 題型自動收集：掃 [data-qid][data-qtype]（見資料規範 §2）=====
  function safeVal(v){return v===undefined?null:v;}
  function autoCollect(){
    var scoreAnswers={}, experienceAnswers={}, openAnswers={}, answers={}, qtypes={};
    document.querySelectorAll('[data-qid]').forEach(function(el){
      var q=el.getAttribute('data-qid'), qtype=el.getAttribute('data-qtype')||'open';
      var given=null;
      var tag=el.tagName.toLowerCase();
      if(tag==='input'||tag==='textarea'||tag==='select'){
        if(el.type==='checkbox'){ if(el.checked){ (given=given||[]); given.push(el.value||true); } }
        else if(el.type==='radio'){ if(el.checked) given=el.value; }
        else given=el.value;
      } else {
        var nested=el.querySelector('input,textarea,select');
        var sel=el.querySelectorAll('[data-value].on,[data-value].selected,[data-value][aria-selected="true"]');
        if(sel.length){ var a=Array.prototype.map.call(sel,function(x){return x.getAttribute('data-value');}); given=a.length===1?a[0]:a; }
        else if(nested){ given = (nested.type==='checkbox')?nested.checked:nested.value; }
        else if(el.hasAttribute('data-value')) given=el.getAttribute('data-value');
        else given=el.textContent.trim();
      }
      given=safeVal(given);
      qtypes[q]=qtype; answers[q]=given;
      if(qtype==='open'){ openAnswers[q]=given; return; }
      var correctRaw=el.getAttribute('data-correct');
      var correct=correctRaw==null?null:(correctRaw.indexOf('、')>=0?correctRaw.split('、'):correctRaw);
      var rec={given:given, correct:correct, isCorrect: (correct==null||given==null)?false:(norm(given)===norm(correct))};
      if(qtype==='score')experienceOrScore(scoreAnswers,q,rec); else experienceOrScore(experienceAnswers,q,rec);
    });
    function experienceOrScore(bucket,q,rec){bucket[q]=rec;}
    return {answers:answers, qtypes:qtypes, scoreAnswers:scoreAnswers, experienceAnswers:experienceAnswers, openAnswers:openAnswers};
  }
  function computeStats(cats){
    var sKeys=Object.keys(cats.scoreAnswers), eKeys=Object.keys(cats.experienceAnswers);
    var sCorrect=sKeys.filter(function(k){return cats.scoreAnswers[k].isCorrect;}).length;
    var eAnswered=eKeys.filter(function(k){var g=cats.experienceAnswers[k].given;return g!=null && g!=='' && !(Array.isArray(g)&&!g.length);}).length;
    return {
      accuracyRate: sKeys.length? Math.round(sCorrect/sKeys.length*100) : null,
      experienceCompletion: eKeys.length? Math.round(eAnswered/eKeys.length*100) : 0
    };
  }

  var BAR_CSS = ''
    + '.ssb{max-width:680px;margin:24px auto;padding:18px 20px;border:2px solid #c7d2fe;border-radius:16px;background:#f8f9ff;font-family:inherit}'
    + '.ssb h3{margin:0 0 4px;font-size:18px;color:#3730a3}'
    + '.ssb p{margin:0 0 12px;font-size:13px;color:#64748b}'
    + '.ssb button{font:inherit;font-weight:800;font-size:16px;width:100%;padding:11px;border:0;border-radius:10px;background:#4f46e5;color:#fff;cursor:pointer}'
    + '.ssb button:hover{background:#4338ca}.ssb button:disabled{opacity:.6;cursor:default}'
    + '.ssb .stat{margin-top:10px;font-size:13px;font-weight:700;min-height:18px}'
    + '.ssb.done{border-color:#86efac;background:#f0fdf4}.ssb.done h3{color:#15803d}';

  function sanitizeId(v){return String(v).replace(/[^0-9]/g,'')||'0';}

  function render(opts, db, auth){
    var wrap=document.createElement('div'); wrap.className='ssb';
    wrap.innerHTML=''
      +'<h3>完成了嗎？繳交學習單</h3>'
      +'<p>按下方按鈕前，請確認上方「我是誰」（年級/班級/學號）已填好。送出後老師就看得到。</p>'
      +'<button id="ssb-go">繳交學習單</button>'
      +'<div class="stat" id="ssb-stat"></div>';
    var mount = opts.mount && document.querySelector(opts.mount);
    (mount||document.body).appendChild(wrap);

    var stat=wrap.querySelector('#ssb-stat');
    wrap.querySelector('#ssb-go').onclick=function(){
      var idn=getIdentity();
      if(!identityValid(idn)){stat.style.color='#b45309';stat.textContent='請先在最上方填好年級、班級、學號（都是數字）。';
        var bar=document.getElementById('wkIdentityBar');if(bar)bar.scrollIntoView({behavior:'smooth',block:'center'});return;}
      var cats=(typeof opts.collect==='function')?opts.collect():autoCollect();
      var st=computeStats(cats);
      var openCount=Object.keys(cats.openAnswers||{}).length;
      var confirmMsg='確定要繳交嗎？\n'
        +(st.accuracyRate!=null?('正確率：'+st.accuracyRate+'%\n'):'')
        +'體驗完成度：'+st.experienceCompletion+'%\n'
        +(openCount?('開放題：'+openCount+' 題已填寫\n'):'')
        +'送出後這份會被老師看到，確定要交嗎？';
      if(!confirm(confirmMsg))return;

      var docId=opts.worksheetId+'__'+sanitizeId(idn.grade)+'-'+sanitizeId(idn.className)+'-'+sanitizeId(idn.studentId);
      var payload={worksheetId:opts.worksheetId,worksheetTitle:opts.title||opts.worksheetId,lessonPath:opts.lessonPath||'',
        grade:idn.grade,className:idn.className,studentId:idn.studentId,
        answers:cats.answers,qtypes:cats.qtypes,
        scoreAnswers:cats.scoreAnswers,experienceAnswers:cats.experienceAnswers,openAnswers:cats.openAnswers,
        accuracyRate:st.accuracyRate,experienceCompletion:st.experienceCompletion,
        status:'submitted',submittedAt:global.firebase.firestore.FieldValue.serverTimestamp()};
      var btn=wrap.querySelector('#ssb-go');btn.disabled=true;stat.style.color='#4f46e5';stat.textContent='繳交中…';
      var write=function(){return db.collection('submissions').doc(docId).set(payload,{merge:true});};
      var p=auth?ensureAuth(auth).then(write):write();
      p.then(function(){
        wrap.classList.add('done');
        wrap.querySelector('h3').textContent='已繳交，完成！';
        wrap.querySelector('p').textContent='你的作答已送給老師（'+idn.grade+'年'+idn.className+'班'+idn.studentId+'號）。如需修改，改完再按一次即可覆蓋。';
        btn.disabled=false;btn.textContent='重新繳交（覆蓋）';stat.style.color='#15803d';
        stat.textContent=(st.accuracyRate!=null?('正確率 '+st.accuracyRate+'% · '):'')+'體驗完成度 '+st.experienceCompletion+'%';
        if(typeof opts.onSubmitted==='function')opts.onSubmitted(payload);
      }).catch(function(e){btn.disabled=false;stat.style.color='#b45309';
        stat.textContent='繳交失敗：'+e.message+'（老師可能尚未部署 Firestore 規則）';});
    };
  }

  var StudentSubmit={
    init:function(opts){
      if(!opts||!opts.worksheetId){console.error('StudentSubmit.init 需要 worksheetId');return;}
      injectIdentityBar();
      var style=document.createElement('style');style.textContent=BAR_CSS;document.head.appendChild(style);
      ensureFirebase(opts.firebaseConfig).then(function(){
        var db=global.firebase.firestore(), auth=global.firebase.auth?global.firebase.auth():null;
        render(opts, db, auth);
      }).catch(function(e){console.error('StudentSubmit：Firebase 載入失敗',e);});
    },
    // 開放題即時同儕動態（留言牆）；見 引導規範/學習單資料與提交規範.md §4
    liveFeed:function(opts){
      if(!opts||!opts.worksheetId||!opts.qid){console.error('StudentSubmit.liveFeed 需要 worksheetId 與 qid');return;}
      var css='.wkfeed{max-width:680px;margin:14px auto;border:2px solid #ddd6fe;border-radius:14px;background:#fff;overflow:hidden;font-family:inherit}'
        +'.wkfeed h4{margin:0;padding:10px 16px;background:#f5f3ff;color:#5b21b6;font-size:13px;font-weight:800}'
        +'.wkfeed .list{max-height:220px;overflow-y:auto;padding:10px 16px}'
        +'.wkfeed .msg{background:#f8fafc;border-radius:10px;padding:8px 12px;margin-bottom:8px;font-size:13px;color:#334155}'
        +'.wkfeed .msg b{color:#7c3aed;font-size:11px;display:block;margin-bottom:2px}'
        +'.wkfeed .empty{font-size:12px;color:#94a3b8;padding:8px 0}';
      var style=document.createElement('style');style.textContent=css;document.head.appendChild(style);
      var wrap=document.createElement('div');wrap.className='wkfeed';
      wrap.innerHTML='<h4>同學們的想法</h4><div class="list" id="wkfeed-list"><div class="empty">還沒有人送出…</div></div>';
      var mount=opts.mount&&document.querySelector(opts.mount);(mount||document.body).appendChild(wrap);
      ensureFirebase(opts.firebaseConfig).then(function(){
        var db=global.firebase.firestore(), auth=global.firebase.auth();
        return ensureAuth(auth).then(function(){
          db.collection('feeds').doc(opts.worksheetId).collection('messages')
            .where('qid','==',opts.qid).orderBy('at','desc').limit(50)
            .onSnapshot(function(qs){
              var list=document.getElementById('wkfeed-list');
              if(qs.empty){list.innerHTML='<div class="empty">還沒有人送出…</div>';return;}
              var html='';qs.forEach(function(d){var m=d.data();
                html+='<div class="msg">'+(m.tag?('<b>'+m.tag+'</b>'):'')+String(m.text||'').replace(/[&<>]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;'}[c];})+'</div>';});
              list.innerHTML=html;
            },function(e){console.warn('liveFeed 讀取失敗',e);var list=document.getElementById('wkfeed-list');if(list)list.innerHTML='<div class="empty">現在看不到同學的留言，晚點再來看看。</div>';});
        });
      }).catch(function(e){console.warn('liveFeed 初始化失敗',e);});
      return {
        post:function(text){
          if(!text||!text.trim())return Promise.resolve();
          return ensureFirebase(opts.firebaseConfig).then(function(){
            var db=global.firebase.firestore(), auth=global.firebase.auth();
            var idn=getIdentity(); var tag=identityValid(idn)?(idn.grade+'年'+idn.className+'班'):'';
            return ensureAuth(auth).then(function(){
              return db.collection('feeds').doc(opts.worksheetId).collection('messages').add(
                {qid:opts.qid,text:String(text).slice(0,200),tag:tag,at:global.firebase.firestore.FieldValue.serverTimestamp()});
            });
          });
        }
      };
    }
  };
  global.StudentSubmit=StudentSubmit;
})(window);
