# -*- coding: utf-8 -*-
"""
自動更新（GitHub 託管）——見《引導規範/自動更新規範.md》。

原理：每一台安裝端都是這個 GitHub 儲存庫的一份 clone。
- 「檢查更新」＝`git fetch` 後比對本機 HEAD 與 origin/main 差幾個 commit。
- 「立即更新」＝`git merge --ff-only`，**只快轉、不做三方合併**，
  這樣永遠不會在老師的電腦上跳出衝突要他解。

之所以敢只用快轉：所有「這台電腦自己的」狀態（config.json／timetable.json／runtime…）
都已列在 .gitignore，安裝端的工作區理論上永遠是乾淨的，快轉一定成功。
真的髒掉（有人手動改過程式碼）就**明講並停手**，不自作主張 stash 或覆蓋。
"""
import os
import subprocess
from pathlib import Path

BRANCH = "main"


def _env():
    e = dict(os.environ)
    # 別讓 git 在伺服器背景跳帳密框把整個請求卡死
    e.setdefault("GIT_TERMINAL_PROMPT", "0")
    e.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new")
    return e


def _git(args, cwd, timeout=90):
    try:
        r = subprocess.run(["git"] + args, cwd=str(cwd), capture_output=True,
                           timeout=timeout, env=_env())
        return (r.returncode,
                r.stdout.decode("utf-8", "replace").strip(),
                r.stderr.decode("utf-8", "replace").strip())
    except FileNotFoundError:
        return 127, "", "這台電腦沒有安裝 git"
    except subprocess.TimeoutExpired:
        return 124, "", "git 執行逾時（網路可能不通）"


def _version(root, ref=None):
    """VERSION 檔的內容＝給人看的版本號；給 ref 就讀那個 ref 上的版本。"""
    if ref:
        rc, out, _ = _git(["show", f"{ref}:VERSION"], root, timeout=30)
        return out.strip() if rc == 0 else ""
    try:
        return (Path(root) / "VERSION").read_text("utf-8").strip()
    except Exception:
        return ""


def _not_git(root):
    return not (Path(root) / ".git").exists()


def check_update(root, branch=BRANCH):
    """回 {ok,isGit,behind,currentVersion,latestVersion,changes[],dirty}。
    behind>0 就是有新版可更新。這個函式只讀不寫，隨時可呼叫。"""
    root = Path(root)
    if _not_git(root):
        return {"ok": True, "isGit": False, "behind": 0,
                "message": "這份安裝不是用 git 取得的（可能是直接複製資料夾過來），"
                           "所以沒辦法自動更新。改用 git clone 安裝一次，之後就能一鍵更新。"}
    rc, _, err = _git(["fetch", "--quiet", "origin", branch], root)
    if rc != 0:
        return {"ok": False, "isGit": True, "error": "連不上 GitHub：" + (err or "fetch 失敗")}
    rc, behind_out, _ = _git(["rev-list", "--count", f"HEAD..origin/{branch}"], root, timeout=30)
    behind = int(behind_out or 0) if (rc == 0 and behind_out.isdigit()) else 0
    changes = []
    rc, log, _ = _git(["log", "--pretty=%h|%ad|%s", "--date=short",
                       f"HEAD..origin/{branch}"], root, timeout=30)
    if rc == 0 and log:
        for line in log.splitlines()[:30]:
            parts = line.split("|", 2)
            if len(parts) == 3:
                changes.append({"sha": parts[0], "date": parts[1], "msg": parts[2]})
    _, dirty, _ = _git(["status", "--porcelain"], root, timeout=30)
    dirty = dirty.strip()
    return {"ok": True, "isGit": True, "behind": behind,
            "currentVersion": _version(root),
            "latestVersion": _version(root, f"origin/{branch}") or _version(root),
            "changes": changes,
            "dirty": bool(dirty),
            "dirtyFiles": [l[3:] for l in dirty.splitlines()[:10]] if dirty else []}


def apply_update(root, branch=BRANCH):
    """只做快轉更新。有本機未提交的修改就停手不動，把檔名列給使用者看。"""
    root = Path(root)
    if _not_git(root):
        return {"ok": False, "error": "這份安裝不是用 git 取得的，無法自動更新。"}
    _, dirty, _ = _git(["status", "--porcelain"], root, timeout=30)
    if dirty.strip():
        files = "\n".join(l[3:] for l in dirty.strip().splitlines()[:10])
        return {"ok": False,
                "error": "這台電腦有還沒提交的修改，為了不蓋掉你的東西，先不更新。\n"
                         "請先處理這些檔案再更新：\n" + files}
    rc, _, err = _git(["fetch", "--quiet", "origin", branch], root)
    if rc != 0:
        return {"ok": False, "error": "連不上 GitHub：" + (err or "fetch 失敗")}
    before = _version(root)
    rc, out, err = _git(["merge", "--ff-only", f"origin/{branch}"], root)
    if rc != 0:
        return {"ok": False,
                "error": "更新失敗：無法快轉（這台電腦可能自己 commit 過東西）。\n" + (err or out)}
    return {"ok": True, "needRestart": True,
            "fromVersion": before, "version": _version(root),
            "message": "已更新到最新版，請關掉視窗重新啟動。"}
