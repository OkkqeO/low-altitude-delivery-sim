"""Replace the single unsigned pledge page with a user-provided paper-signed scan.

This utility does not create or authenticate signatures. It preserves the input
files and writes a new PDF plus an audit sidecar. Authoring dependency: pypdf.
"""
from pathlib import Path
import argparse,hashlib,json
from pypdf import PdfReader,PdfWriter

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--report',type=Path,required=True)
    ap.add_argument('--signed-commitment',type=Path,required=True,help='真实全员手写签字并扫描的一页PDF')
    ap.add_argument('--output',type=Path,required=True,help='新输出PDF，不能覆盖输入')
    args=ap.parse_args()
    src=args.report.resolve(strict=True);scan=args.signed_commitment.resolve(strict=True);out=args.output.resolve()
    if out in (src,scan) or out.exists():ap.error('输出须为不同且尚不存在的新文件')
    if src==scan:ap.error('报告与签字扫描必须是不同文件')
    reader=PdfReader(src);signed=PdfReader(scan)
    if reader.is_encrypted or signed.is_encrypted:ap.error('请使用可读取的非加密PDF')
    if len(signed.pages)!=1:ap.error('签字扫描须为一页；请先核对官方承诺书完整性')
    if any(f.get('/FT')=='/Sig' for f in (signed.get_fields() or {}).values()):ap.error('本工具仅接收纸质签字扫描，不重写数字签名PDF')
    candidates=[i for i,p in enumerate(reader.pages) if '中国仿真创新应用大赛诚信承诺书' in (p.extract_text() or '').replace(' ','')]
    if len(candidates)!=1:ap.error('无法唯一定位承诺书，请核对报告文本；没有修改任何输入')
    index=candidates[0];writer=PdfWriter()
    for i,page in enumerate(reader.pages):writer.add_page(signed.pages[0] if i==index else page)
    writer.add_metadata({'/Title':str(reader.metadata.title or '参赛主报告')})
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open('xb') as f:writer.write(f)
    check=PdfReader(out)
    if len(check.pages)!=len(reader.pages):raise RuntimeError('输出页数核验失败')
    proof={'report_sha256':digest(src),'provided_scan_sha256':digest(scan),'output_sha256':digest(out),'replaced_one_based_page':index+1,'page_count':len(check.pages),'signature_authentication':'not performed; human verification required'}
    out.with_suffix('.merge.json').write_text(json.dumps(proof,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(proof,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
