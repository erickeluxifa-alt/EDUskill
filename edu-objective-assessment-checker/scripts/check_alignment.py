#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""check_alignment.py v1.0"""
import argparse,csv,json,re,sys
from dataclasses import dataclass,field
from pathlib import Path

LV=["remember","understand","apply","analyze","evaluate","create"]
RK={v:i for i,v in enumerate(LV)}
CN={"remember":"记忆","understand":"理解","apply":"应用",
    "analyze":"分析","evaluate":"评价","create":"创造","unknown":"未识别"}
SW=set("的了和与及在是对由从为以而这那一个种类等中上下内外".split())

@dataclass
class Obj:id:str;text:str;bloom:str="unknown"
@dataclass
class Itm:id:str;text:str;p:float=1.0;e:list=field(default_factory=list)

def lv(p):
 d=json.loads(open(p,'r',encoding='utf-8').read())
 return {k.lower():[v.strip().replace('...','')for v in vs]for k,vs in d['verbs_by_level'].items()}

def cl(t,d):
 if not t:return("u",-1)
 n=re.sub(r'\s+','',t.lower());b="u";br=-99
 for x in LV:
  sv=sorted(set(v for v in d.get(x,[])if v),key=lambda z:-len(z))
  if not any(v!=""and v.lower()in n for v in sv):continue
  r=RK[x]
  if r>br:br=r;b=x
 return(b,max(br,-1))

def dp(k):return CN.get((k or'').lower(),"?")

def hi(k):
 k=(k or'').lower()
 return RK.get(k,-1)>=3

def sw_ch_set():
 r=set()
 for w in SW:r.update(w);r.add(" ")
 return r|set(list("0123456789abcdefxyzXYZ"))
SC=sw_ch_set()

def bg(s):
 s=s or ""
 out=set()
 prev=None
 for ch in s:
  if ch in SC:
   prev=None;continue
  if prev is None:
   prev=ch;continue
  bi=prev+ch
  if bi not in SW and any(c not in SC for c in bi):
   out.add(bi)
  prev=ch
 return out

def nid(rv,pf,fb):
 s=str(rv or'').strip().upper().replace('#','').replace('.','')
 m=re.match(r'^([A-Z])(\d+)$',s)
 if m:
  l=m.group(1);d=m.group(2);e=pf.upper()
  if l!=e:l=e
  return f"{l}{d}"
 elif s.isdigit():return f"{pf.upper()}{int(s)}"
 else:return f"{pf.upper()}{fb}"

def pj(jp,d):
 try:
  raw=json.loads(open(jp,'r',encoding='utf-8').read())
 except FileNotFoundError:
  sys.stderr.write(f"[ERR] 文件不存在:{jp}\n");sys.exit(2)
 except json.JSONDecodeError as e:
  sys.stderr.write(f"[ERR] JSON 解析失败:{e.msg}\n");sys.exit(3)

 c=raw.get('course_name')or raw.get('course')
 u=raw.get('unit_name')or raw.get('unit')or raw.get('module')

 ob=None
 for kk in ('objectives','learning_objectives','goals'):
  vv_=raw.get(kk)
  if vv_ is not None and len(vv_)>0:ob=vv_;break
 if ob is None:
  sys.stderr.write("[ERR] 缺少 objectives/learning_objectives/goals 任一字段或为空\n")
  sys.exit(3)

 im=None
 for kk in ('items','assessments','questions'):
  v=raw.get(kk)
  if v is not None and len(v)>0:im=v;break
 if im is None:
  sys.stderr.write("[ERR] 缺少 items/assessments/questions 任一字段或为空\n")
  sys.exit(3)

 objs=[]
 for i,r in enumerate(ob,start=1):
  oid=nid(r.get('id',f'O{i}'),'O',i)
  tx=r.get('text')or r.get('description')or''
  if not tx.strip():
   sys.stderr.write(f"[ERR] objective #{i} text/description 为空\n");sys.exit(3)
  b,_rk=cl(tx,d);objs.append(Obj(id=oid,text=str(tx),bloom=b))
 its=[]
 for j,r in enumerate(im,start=1):
  iid=nid(r.get('id',f'Q{j}'),'Q',j)
  tq=r.get('text')or r.get('question')or''
  pt=float(r.get('points')or r.get('score')or r.get('weightage')or 1.0)
  ei=[nid(e,'O',0)for e in(r.get('explicit_objective_ids')or[])]
  its.append(Itm(id=iid,text=str(tq),p=pt,e=ei))
 return c,u,objs,its

def mx(objs,its):
 res=[]
 for o in objs:
  ob=bg(o.text);row=[]
  for it in its:
   f=False;r=""
   if o.id in it.e:f=True;r="explicit"
   else:
    ibg=bg(it.text)
    common=ob & ibg
    meaningful=[x for x in common
                if not any(c in SC for c in x)]
    if len(meaningful)>0:f=True;r=f"bigram:{sorted(meaningful)[0]}"
   row.append({"obj":o.id,"item":it.id,"m":bool(f),"reason":r})
  res.append(row)
 return res

def dg(c,u,o,i,m,d):
 unc=[];orph=set(it.id for it in i);mm=[]
 iby={it.id:it for it in i}
 for idx,row in enumerate(m):
  ob=o[idx];cv=False
  for cc in row:
   if cc["m"]:
    cv=True;orph.discard(cc["item"])
    io_obj=iby[cc["item"]]
    ilvl,_ir=cl(io_obj.text,d)
    desc=""
    ol=ob.bloom;il=ilvl
    if hi(ol)and not hi(il):desc=f"目标高阶但试题低阶"
    elif hi(il)and not hi(ol):desc=f"目标低阶但试题高阶"
    if desc:mm.append((cc["obj"],cc["item"],f"{dp(ol)}→{dp(il)}"))
  if not cv:unc.append(ob.id)
 cr=(len(o)-len(unc))/max(len(o),1)
 ar=sum(sum(1 for c in row if c["m"])for row in m)/max(len(o)*max(len(i),1),1)
 sc=max(0,min(100,
     round(cr*40+ar*30-
           min(len(mm)/5*10,10)+
           (-15*min(len(orph)/max(len(i),1),1)),1)))
 sgs=[]
 if unc:sgs.append(f"目标{','.join(unc)}未被覆盖")
 if orph:sgs.append(f"题目{','.join(sorted(orph))}未关联目标")
 ho=[ob.id for ob in o if hi(ob.bloom)]
 li=[io.id for io in i if not hi(cl(io.text,d)[0])]
 if ho and len(li)>len(i)//2:
  sgs.append("建议为高阶认知目标补充分析/评价/创造类试题")
 return {"c":c,"u":u,"unc":unc,"orph":sorted(list(orph)),"mm":mm,
         "cr":cr,"ar":ar,"sc":sc,"sgs":sgs}


def md(r,objs,its,m):
 L=[]
 L.append(f"# 教学目标-评估一致性诊断报告")
 if r["c"]:L.append(f"\n**课程**：{r['c']}")
 if r["u"]:L.append(f"  **单元**：{r['u']}")
 L.append(f"\n## 一、概览\n")
 L.append(f"- 学习目标数：{len(objs)}")
 L.append(f"- 测验题数：{len(its)}")
 L.append(f"- 综合评分：**{r['sc']} /100**")
 L.append(f"- 覆盖率：{r['cr']*100:.1f}%")
 L.append(f"- 平均匹配率：{r['ar']*100:.1f}%")

 L.append("\n## 二、学习目标 Bloom 分布\n")
 L.append("|编号|描述|认知层级|")
 L.append("|---|---|---|")
 for o in objs:
  L.append(f"|{o.id}|{o.text}|{dp(o.bloom)}|")

 L.append("\n## 三、覆盖矩阵\n")
 hdr=["目标\\题"]+[it.id for it in its]
 L.append("|"+"|".join(hdr)+"|")
 L.append("|"+ "|".join(["---"]*len(hdr))+"|")
 for idx,row in enumerate(m):
  ob=objs[idx]
  cells=[ob.id]
  for cc in row:
   mark="✓"if cc["m"]else""
   reason=f"<br><sub>{cc['reason']}</sub>"if cc["m"]else ""
   cells.append(f"{mark}{reason}")
  L.append("|"+"|".join(cells)+"|")

 L.append("\n## 四、诊断结果\n")
 if r["unc"]:
  L.append("### 未被覆盖的目标\n")
  for oid in r["unc"]:
   ob=next(o for o in objs if o.id==oid)
   L.append(f"- **{oid}**: {ob.text}")
 else:L.append("- 所有目标均已被至少一道题目覆盖 ✓\n")

 if r["orph"]:
  L.append("\n### 未关联到目标的题目\n")
  for iid in r["orph"]:
   io=next(it for it in its if it.id==iid)
   L.append(f"- **{iid}** ({io.p}分): {io.text}")
 else:
  L.append("\n- 所有题目均已关联到至少一个目标 ✓\n")

 if r["mm"]:
  L.append("\n### 认知层级失配对\n")
  for tup_ in r["mm"]:
   L.append(f"- 目标 {tup_[0]} ↔ 题目 {tup_[1]}：{tup_[2]}")

 L.append("\n## 五、干预建议\n")
 for sgs_line in r["sgs"]:
  L.append(f"- {sgs_line}")
 return "\n".join(L)

def csv_out(m,o,i,fp):
 with open(fp,'w',encoding='utf-8',newline='')as f:
  w=csv.writer(f)
  w.writerow(["obj_id","item_id","matched","reason"])
  for row in m:
   for c in row:
    w.writerow([c["obj"],c["item"],c["m"],c["reason"]])

def js_out(r,objs,its,m,fp):
 d={"course_name":r.get('c'),"unit_name":r.get('u'),
    "integrity_score":r["sc"],"coverage_rate":round(r["cr"],3),
    "avg_match_rate":round(r["ar"],3),
    "uncovered_objective_ids":list(r["unc"]),
    "orphan_item_ids":sorted(list(r["orph"])),
    "mismatch_pairs":[{"obj_id":t[0],"item_id":t[1]}for t in r["mm"]],
    "suggestions":list(r["sgs"]),
    "objectives":[{"id":ob.id,"text":ob.text,"bloom_level":ob.bloom}for ob in objs],
    "items":[{"id":it.id,"text":it.text,"points":it.p,"explicit_obj_ids":it.e}for it in its],
    }
 json.dump(d,open(fp,'w',encoding='utf-8'),ensure_ascii=False,indent=2)

def main():
 ap=argparse.ArgumentParser(description="教学目标-评估一致性诊断引擎 v1.0")
 ap.add_argument('--json',required=True,type=Path,help="JSON 输入文件路径")
 ap.add_argument('--bloom',required=True,type=Path,help="布鲁姆动词字典 JSON")
 ap.add_argument('--out-dir',type=Path,default=Path('./output'))
 args=ap.parse_args()

 vd=lv(args.bloom);c,u,o,it=pj(args.json,vd);
 m=mx(o,it);res=dg(c,u,o,it,m,vd);

 args.out_dir.mkdir(parents=True,exist_ok=True)
 fp_md=args.out_dir/'alignment_report.md'
 open(fp_md,'w',encoding='utf-8').write(md(res,o,it,m))
 csv_out(m,o,it,args.out_dir/'coverage_matrix.csv')
 js_out(res,o,it,m,args.out_dir/'summary.json')
 print(f"[OK] 已生成：{fp_md}")
 print(f"[OK] 完整性评分={res['sc']}/100，覆盖率={res['cr']*100:.0f}%，平均匹配率={res['ar']*100:.0f}%")

if __name__=='__main__':sys.exit(main())
