"""Create/push only a PRIVATE GitHub repository, then upload a private prerelease.

Requires GitHub CLI authentication in the user's normal Windows session. Tokens
are handled by gh; this script never reads, prints or stores credential contents.
"""
import argparse,hashlib,json,shutil,subprocess,sys,zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
REPOSITORY='PCB-Manufacturing-Studio'
TAG='v0.3.0-rc.1'


def run(args,capture=False,check=True):
    result=subprocess.run([str(a) for a in args],cwd=ROOT,text=True,encoding="utf-8",capture_output=capture)
    if check and result.returncode:raise RuntimeError('Command failed: '+str(args[0])+' '+str(args[1]))
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gh-path',default=shutil.which('gh'))
    parser.add_argument('--artifact',type=Path,required=True)
    args=parser.parse_args();gh=args.gh_path
    if not gh:raise ValueError('Install the official GitHub CLI or provide --gh-path.')
    artifact=args.artifact.resolve();checksum=artifact.with_suffix('.zip.sha256')
    if not artifact.is_file() or not checksum.is_file():raise ValueError('Portable ZIP and its checksum are required.')
    expected=checksum.read_text(encoding='ascii').split()[0]
    if hashlib.sha256(artifact.read_bytes()).hexdigest()!=expected:raise ValueError('Portable ZIP checksum mismatch.')
    head=run(['git','rev-parse','HEAD'],True).stdout.strip()
    if run(['git','status','--porcelain'],True).stdout.strip():raise ValueError('Review/commit source changes before publishing this milestone.')
    with zipfile.ZipFile(artifact) as archive:
        manifest=json.loads(archive.read('PCB Isolator/BUILD-MANIFEST.json'))
    if manifest['git_commit']!=head:raise ValueError('Portable archive was not built from the current commit.')
    if run([gh,'auth','status'],True,False).returncode:
        print('GitHub sign-in is required. Follow the browser/device sign-in prompts; never paste tokens into chat.',flush=True)
        run([gh,'auth','login','--hostname','github.com','--web','--git-protocol','https','--skip-ssh-key'])
    account=json.loads(run([gh,'api','user'],True).stdout);owner=account['login'];slug=owner+'/'+REPOSITORY
    print('Authenticated account: '+owner+'; target: '+slug+' (PRIVATE only)',flush=True)
    view=run([gh,'repo','view',slug,'--json','isPrivate,url'],True,False)
    if view.returncode:
        run([gh,'repo','create',slug,'--private','--description','Windows app for KiCad PCB manufacturing: laser isolation, CNC drilling/profile toolpaths, reviews and calibration.'])
        view=run([gh,'repo','view',slug,'--json','isPrivate,url'],True)
    repo=json.loads(view.stdout)
    if repo.get('isPrivate') is not True:raise ValueError('Refusing to push: the target repository is not private.')
    url=repo['url']+'.git';remote=run(['git','remote','get-url','origin'],True,False)
    if remote.returncode:run(['git','remote','add','origin',url])
    elif remote.stdout.strip().removesuffix('.git')!=url.removesuffix('.git'):raise ValueError('Existing origin differs from the chosen repository; nothing was overwritten.')
    # Per-command helper avoids modifying the user's global Git/GCM configuration.
    helper='!"'+str(Path(gh).resolve()).replace('\\','/')+'" auth git-credential'
    git=['git','-c','credential.helper=','-c','credential.helper='+helper]
    run(git+['push','-u','origin','main'])
    existing=run(['git','rev-parse',TAG+'^{}'],True,False)
    if existing.returncode:run(['git','tag','-a',TAG,'-m','Single-sided manufacturing baseline'])
    elif existing.stdout.strip()!=head:raise ValueError('Milestone tag already points to a different commit.')
    run(git+['push','origin',TAG])
    if run([gh,'release','view',TAG,'--repo',slug],True,False).returncode==0:
        print('Private release already exists; assets were not overwritten. Inspect it before replacing anything.')
    else:
        run([gh,'release','create',TAG,'--repo',slug,'--verify-tag','--prerelease','--title','0.3.0-rc.1 - single-sided manufacturing baseline','--notes-file',ROOT/'docs/release-notes.md',artifact,checksum])
    verified=json.loads(run([gh,'repo','view',slug,'--json','isPrivate,url'],True).stdout)
    if verified['isPrivate'] is not True:raise ValueError('Unexpected repository visibility after upload.')
    print('PRIVATE repository ready: '+verified['url'])
    print('Private prerelease: '+verified['url']+'/releases/tag/'+TAG)


if __name__=='__main__':
    try:main()
    except Exception as error:print('Stopped: '+str(error),file=sys.stderr);sys.exit(1)
