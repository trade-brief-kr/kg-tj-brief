#!/usr/bin/env python3
"""국가 약황 탭 생성: tools/profile/profile.html의 {{REF}} 표기를 refs.py 링크로 바꿔 index.html의 <!--PROFILE--> 구간에 넣는다.
사용법: python3 tools/profile/build_profile.py"""
import re, html, sys
import os; HERE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,HERE); os.chdir(HERE)
from refs import REFS
t=open('profile.html',encoding='utf-8').read()
used=[]
def rep(m):
    k=m.group(1)
    if k=='REFLIST': return m.group(0)
    if k not in REFS: raise SystemExit('missing ref '+k)
    if k not in used: used.append(k)
    title,url=REFS[k]
    return f'<a class="ref" href="{html.escape(url)}" target="_blank" rel="noopener" title="{html.escape(title)}">[{k}]</a>'
t=re.sub(r'\{\{(\w+)\}\}',rep,t)
lst=''.join(f'<li><b>[{k}]</b> <a href="{html.escape(REFS[k][1])}" target="_blank" rel="noopener">{html.escape(REFS[k][0])}</a></li>' for k in used)
t=t.replace('{{REFLIST}}',lst)
idx=open('../../index.html',encoding='utf-8').read()
idx=re.sub(r'(?s)<!--PROFILE-->.*<!--/PROFILE-->','<!--PROFILE-->\n'+t+'<!--/PROFILE-->',idx)
open('../../index.html','w',encoding='utf-8').write(idx)
print('refs used',len(used))
