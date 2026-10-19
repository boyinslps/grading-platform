"""建立「本機白板辨識」環境 ocr-runtime/（RapidOCR＋ONNX Runtime，離線辨識，不送 LLM）。

由「安裝本機辨識.bat」呼叫，也可直接：runtime\\python\\python.exe install_ocr.py
做的事：複製一份可攜 Python → 啟用 site-packages → 安裝 pip → pip install rapidocr onnxruntime → 暖機（下載模型）。
全部在 ocr-runtime/ 裡，不動原本的 runtime/、也不動系統 Python。需要網路，約 320 MB、幾分鐘；裝完辨識就不需要網路。
資料夾已列 .gitignore，換電腦時重跑一次即可。
"""
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEST = HERE / "ocr-runtime"
GET_PIP = "https://bootstrap.pypa.io/get-pip.py"


def base_python_dir():
    for c in (HERE / "runtime" / "python", HERE.parent / "工作台" / "runtime" / "python"):
        if (c / "python.exe").is_file():
            return c
    for d in HERE.parent.iterdir():
        c = d / "runtime" / "python"
        if (c / "python.exe").is_file():
            return c
    return None


def run(*cmd):
    print(">", " ".join(str(c) for c in cmd), flush=True)
    r = subprocess.run([str(c) for c in cmd])
    if r.returncode != 0:
        sys.exit("失敗（結束碼 %d）" % r.returncode)


def main():
    py = DEST / "python.exe"
    if not py.is_file():
        base = base_python_dir()
        if not base:
            sys.exit("找不到可攜 Python（需要 runtime\\python 或旁邊工作台的 runtime\\python）。")
        print("複製可攜 Python：%s → %s" % (base, DEST), flush=True)
        shutil.copytree(base, DEST)
        for pth in DEST.glob("python*._pth"):
            lines = pth.read_text("utf-8").splitlines()
            lines = [("import site" if l.strip() == "#import site" else l) for l in lines]
            if "Lib/site-packages" not in lines:
                lines.append("Lib/site-packages")
            pth.write_text("\n".join(lines) + "\n", "utf-8")
    try:
        subprocess.run([str(py), "-m", "pip", "--version"], check=True, capture_output=True)
    except Exception:
        gp = DEST / "get-pip.py"
        print("下載 pip 安裝程式：", GET_PIP, flush=True)
        urllib.request.urlretrieve(GET_PIP, gp)
        run(py, gp, "--no-warn-script-location")
        gp.unlink()
    run(py, "-m", "pip", "install", "--no-warn-script-location", "rapidocr", "onnxruntime")
    print("暖機（第一次會下載辨識模型）…", flush=True)
    run(py, "-c", "import logging;logging.disable(logging.CRITICAL);from rapidocr import RapidOCR;RapidOCR();print('OK')")
    print("\n完成。重新啟動評分平台後，「🪑 紀錄 → 上傳白板照片」就會用這個引擎。")


if __name__ == "__main__":
    main()
