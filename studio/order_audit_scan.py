import sys, json, time, importlib.util
sys.path.insert(0,"/Users/denbell/OMPU_Housemaster")
spec=importlib.util.spec_from_file_location("claw","/Users/denbell/OMPU_Housemaster/tools/claw.py")
m=importlib.util.module_from_spec(spec); sys.argv=['claw.py']; spec.loader.exec_module(m)
SP="/private/tmp/claude-501/-Users-denbell-OMPU-Jee/bef040e0-991e-468e-9e3c-a040e3ff81a4/scratchpad/order"
cand=json.load(open(SP+"/candidates.json"))
mycmts=[]; meta={}
for i,pid in enumerate(cand):
    d=m.call("GET",f"/api/v1/posts/{pid}/comments?limit=50")
    cs=d.get("comments") or []
    hit=[c for c in cs if "hausmaster" in str((c.get("author") or {}).get("name")) or "恒猫" in str((c.get("author") or {}).get("display_name"))]
    if hit:
        pd=m.call("GET",f"/api/v1/posts/{pid}"); p=pd.get("post") or pd
        a=p.get("author") or {}
        meta[pid]={"title":(p.get("title") or "")[:70],"author":a.get("display_name") or a.get("name"),
                   "circle":(p.get("circle") or {}).get("name_en") if isinstance(p.get("circle"),dict) else None,
                   "created_at":p.get("created_at"),"upvotes":p.get("upvotes")}
        for c in hit:
            mycmts.append({"comment_id":c["id"],"post_id":pid,"created_at":c["created_at"],
                           "parent_id":c.get("parent_id"),"upvotes":c.get("upvotes"),
                           "post_author":meta[pid]["author"],"post_title":meta[pid]["title"],
                           "circle":meta[pid]["circle"],"len":len(c.get("content") or "")})
    print(f"{i+1}/{len(cand)} {pid[:8]} hits={len(hit)} running={len(mycmts)}",flush=True)
mycmts.sort(key=lambda x:x["created_at"])
json.dump(mycmts,open(SP+"/my_comments.json","w"),ensure_ascii=False,indent=1)
json.dump(meta,open(SP+"/post_meta.json","w"),ensure_ascii=False,indent=1)
print("DONE MY COMMENTS:",len(mycmts))
