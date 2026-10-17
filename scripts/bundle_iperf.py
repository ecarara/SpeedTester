#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Edson Angelo Carara
"""Build fixed upstream source; ship the native tool and required crypto runtime."""
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shlex
import shutil
import subprocess
import tarfile
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def fetch(entry, destination):
    if not destination.exists():
        request = urllib.request.Request(entry['url'], headers={'User-Agent':'CararaLab-SpeedTester-build'})
        temporary = destination.with_suffix(destination.suffix + '.tmp')
        with urllib.request.urlopen(request, timeout=120) as source, temporary.open('wb') as target:
            shutil.copyfileobj(source, target)
        temporary.replace(destination)
    if hashlib.sha256(destination.read_bytes()).hexdigest() != entry['sha256']:
        raise ValueError('native source checksum mismatch')
    return destination


def run(command, **options):
    return subprocess.check_output(command, text=True, **options).strip()


def build(bundle, version):
    pins = json.loads((ROOT/'security/iperf3.json').read_text())
    work = ROOT/'build/native-iperf'
    work.mkdir(parents=True, exist_ok=True)
    archive = fetch(pins['source'], work/'iperf.tar.gz')
    source = work/('iperf-'+pins['version'])
    if source.exists():
        shutil.rmtree(source)
    with tarfile.open(archive) as package:
        package.extractall(work, filter='data')
    system = platform.system()
    tools = bundle/('Contents/MacOS/tools' if system=='Darwin' else 'tools')
    tools.mkdir(parents=True, exist_ok=True)
    notices = bundle/'THIRD-PARTY-LICENSES/iperf3'
    notices.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source/'LICENSE', notices/'LICENSE')
    # Upstream source accompanies its license and source checksum on every OS.
    shutil.copy2(archive, notices/'iperf-3.22.tar.gz')
    environment = os.environ.copy()
    configure = ['./configure','--disable-shared','--enable-static','--without-sctp']
    bash = None
    if system=='Darwin':
        prefix = run(['/opt/homebrew/bin/brew','--prefix','openssl@3'])
        configure.append('--with-openssl='+prefix)
        crypto_version = run([prefix+'/bin/openssl','version']).split()[1]
    elif system=='Linux':
        configure.append('--with-openssl=/usr')
        crypto_version = run(['openssl','version']).split()[1]
    else:
        msys = Path(environment['SPEEDTESTER_MSYS_ROOT'])
        bash = msys/'usr/bin/bash.exe'
        environment['MSYSTEM'] = 'MSYS'
        environment['CHERE_INVOKING'] = '1'
        command = 'cd '+shlex.quote(source.as_posix())+' && ac_cv_func_SetProcessAffinityMask=no LDFLAGS=-static-libgcc ./configure --disable-shared --enable-static --without-sctp --with-openssl=/usr && make -j2'
        run([str(bash),'-lc',command], env=environment)
        crypto_version = run([str(bash),'-lc','openssl version'], env=environment).split()[1]
    if system!='Windows':
        subprocess.run(configure,cwd=source,env=environment,check=True)
        subprocess.run(['make','-j2'],cwd=source,env=environment,check=True)
    binary = tools/('iperf3.exe' if system=='Windows' else 'iperf3')
    shutil.copy2(source/'src'/binary.name,binary)
    binary.chmod(0o755)
    native = [{'name':'iperf3','version':pins['version'],'source':pins['source']},
              {'name':'openssl','version':crypto_version}]
    if system=='Linux':
        libraries = re.findall(r'=> (/[^ ]+)',run(['ldd',str(binary)]))
        crypto = [p for p in libraries if Path(p).name.startswith('libcrypto.so')]
        if len(crypto)!=1:
            raise ValueError('Expected OpenSSL crypto runtime')
        shutil.copy2(crypto[0],tools/Path(crypto[0]).name)
        subprocess.run(['patchelf','--set-rpath','$ORIGIN',str(binary)],check=True)
        notice=bundle/'THIRD-PARTY-LICENSES/OpenSSL';notice.mkdir(exist_ok=True)
        shutil.copy2('/usr/share/doc/libssl3t64/copyright' if Path('/usr/share/doc/libssl3t64/copyright').exists() else '/usr/share/doc/libssl3/copyright',notice/'copyright')
    elif system=='Darwin':
        libraries=[line.strip().split(' (')[0] for line in run(['/usr/bin/otool','-L',str(binary)]).splitlines()[1:]]
        crypto=[p for p in libraries if Path(p).name.startswith('libcrypto')]
        if len(crypto)!=1:
            raise ValueError('Expected OpenSSL crypto runtime')
        library=tools/Path(crypto[0]).name;shutil.copy2(crypto[0],library)
        subprocess.run(['/usr/bin/install_name_tool','-change',crypto[0],'@loader_path/'+library.name,str(binary)],check=True)
        subprocess.run(['/usr/bin/install_name_tool','-id','@loader_path/'+library.name,str(library)],check=True)
        for item in (library,binary):subprocess.run(['/usr/bin/codesign','--force','--sign','-',str(item)],check=True)
        notice=bundle/'THIRD-PARTY-LICENSES/OpenSSL';notice.mkdir(exist_ok=True)
        shutil.copy2(Path(prefix)/'LICENSE.txt',notice/'LICENSE.txt')
    else:
        # Compile ourselves; copy only known dependency DLLs from the official
        # package installation. The POSIX runtime itself is independently pinned.
        runtime=fetch(pins['windows_runtime'],work/'runtime.pkg.tar.zst')
        extraction=work/'runtime';extraction.mkdir(exist_ok=True)
        command='tar -xf '+shlex.quote(runtime.as_posix())+' -C '+shlex.quote(extraction.as_posix())+' usr/bin/msys-2.0.dll usr/share/doc/Cygwin/COPYING usr/share/doc/Cygwin/CYGWIN_LICENSE'
        run([str(bash),'-lc',command],env=environment)
        shutil.copy2(extraction/'usr/bin/msys-2.0.dll',tools/'msys-2.0.dll')
        pending=[binary];seen=set()
        while pending:
            item=pending.pop()
            imports=re.findall(r'DLL Name:\s*(\S+)',run([str(bash),'-lc','objdump -p '+shlex.quote(item.as_posix())],env=environment))
            for name in imports:
                if not name.lower().startswith('msys-') or name.lower() in seen:continue
                if name.lower() not in ('msys-2.0.dll','msys-crypto-3.dll','msys-z.dll'):
                    raise ValueError('Unexpected native dependency: '+name)
                seen.add(name.lower())
                destination=tools/name
                if name.lower()!='msys-2.0.dll':shutil.copy2(msys/'usr/bin'/name,destination)
                pending.append(destination)
        license_dir=bundle/'THIRD-PARTY-LICENSES/MSYS2';license_dir.mkdir(exist_ok=True)
        for item in (extraction/'usr/share/doc/Cygwin').iterdir():shutil.copy2(item,license_dir/item.name)
        notice=bundle/'THIRD-PARTY-LICENSES/OpenSSL';notice.mkdir(exist_ok=True)
        candidates=list((msys/'usr/share/licenses').glob('openssl*/LICENSE*'))
        if not candidates:candidates=list((msys/'usr/share/doc/openssl').glob('LICENSE*'))
        if not candidates:raise ValueError('OpenSSL license required')
        for item in candidates:shutil.copy2(item,notice/item.name)
        releases=ROOT/'dist/desktop/releases';releases.mkdir(parents=True,exist_ok=True)
        source_name=pins['windows_source']['url'].rsplit('/',1)[1]
        fetch(pins['windows_source'],releases/source_name)
        tag='v0.3.0-desktop-preview.'+version.split('dev')[1]
        (license_dir/'SOURCE.txt').write_text('Corresponding MSYS2 runtime sources, including upstream source and distribution patches:\nhttps://github.com/ecarara/SpeedTester/releases/download/'+tag+'/'+source_name+'\nSHA256: '+pins['windows_source']['sha256']+'\n')
        native.append({'name':'msys2-runtime','version':pins['windows_runtime']['version'],'source':pins['windows_source']})
    # Invoking --version performs no network or measurement. Verify the exact
    # bundled program outside its build directory, without the build PATH.
    isolated={**os.environ,'PATH':str(tools)+os.pathsep+(os.environ.get('SystemRoot',r'C:\Windows')+'/System32' if system=='Windows' else '/usr/bin:/bin')}
    output=run([str(binary),'--version'],cwd=work,env=isolated)
    if 'iperf '+pins['version'] not in output or 'authentication' not in output.lower():
        raise ValueError('Required native version or RSA authentication unavailable')
    files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in tools.iterdir() if p.is_file()}
    (bundle/'iperf-components.json').write_text(json.dumps({'components':native,'files':files,'rsa_authentication':True},indent=2)+'\n')
    inventory=json.loads((bundle/'runtime-components.json').read_text());inventory['native_components']=native
    (bundle/'runtime-components.json').write_text(json.dumps(inventory,indent=2)+'\n')
    cdx={'bomFormat':'CycloneDX','specVersion':'1.5','version':1,'components':[{'type':'library','name':p['name'],'version':p['version'],'purl':'pkg:generic/'+p['name']+'@'+p['version']} for p in native]}
    (bundle/'native-sbom.cdx.json').write_text(json.dumps(cdx,indent=2)+'\n')
    print('Bundled iPerf3 source, RSA support and native dependency inventory verified')
    return binary
