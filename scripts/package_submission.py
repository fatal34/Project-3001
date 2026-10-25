"""Create a local clean-clone ZIP for the user to publish and submit manually."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import zipfile
ROOT=Path(__file__).resolve().parents[1]

def main():
    """Preserve genuine Git history, remove local origin, verify every file."""
    if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip():
        raise RuntimeError('Commit all final project files before creating the clean clone')
    head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip()
    destination=ROOT/'dist';destination.mkdir(exist_ok=True)
    required=['README.md','LICENSE','requirements.txt','src/sensor_project/interpolation.py',
              'data/prepared/environment.csv','reports/MMA3001_Dataset2_technical_report.pdf',
              'reports/test_report.html','docs/html/index.html','docs/github_upload_guide.md',
              'presentation/MMA3001_Dataset2_presentation.pptx','results/selection_frozen.json']
    with tempfile.TemporaryDirectory(prefix='mma3001-dataset2-') as temporary:
        clone=Path(temporary)/'MMA3001_Dataset2_project'
        subprocess.run(['git','clone','--no-hardlinks','--single-branch','--branch','main',str(ROOT),str(clone)],check=True)
        subprocess.run(['git','remote','remove','origin'],cwd=clone,check=True)
        for filename in required:
            if not (clone/filename).is_file():raise RuntimeError(f'Missing required file: {filename}')
        archive=destination/'MMA3001_Dataset2_repository_clone.zip'
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as output:
            for path in sorted(clone.rglob('*')):
                if path.is_file():output.write(path,Path(clone.name)/path.relative_to(clone))
        files=[f for f in subprocess.check_output(['git','ls-files','-z'],cwd=clone).decode().split('\0') if f]
        with zipfile.ZipFile(archive) as output:
            if output.testzip() is not None:raise RuntimeError('ZIP integrity failure')
            prefix=clone.name+'/'
            if output.read(prefix+'.git/refs/heads/main').decode().strip()!=head:
                raise RuntimeError('Archive main commit differs')
            if not all(output.read(prefix+f)==(ROOT/f).read_bytes() for f in files):
                raise RuntimeError('Archive content differs from the final project')
            if b'[remote ' in output.read(prefix+'.git/config'):
                raise RuntimeError('The manual-upload clone must have no remote')
        manifest={'commit':head,'archive':archive.name,'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),
                  'bytes':archive.stat().st_size,'tracked_files_checked':len(files),'contains_git_history':True,
                  'remote_configured':False,'github_upload_performed':False,'required_files_checked':required}
        (destination/'submission_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        print(json.dumps(manifest,indent=2))

if __name__=='__main__':main()
