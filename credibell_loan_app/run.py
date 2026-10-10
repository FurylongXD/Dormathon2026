"""Start the complete local dashboard: python run.py [--port 8502]."""
import argparse
from pathlib import Path
import sys

def main():
    parser=argparse.ArgumentParser(description='CrediBell local loan dashboard')
    parser.add_argument('--port',type=int,default=8502)
    parser.add_argument('--open',action='store_true',help='Open the dashboard when the local server is ready')
    args=parser.parse_args()
    if not 1024<=args.port<=65535: parser.error('Use a port between 1024 and 65535.')
    if sys.version_info<(3,12): parser.error('Install Python 3.12 or newer. Python 3.13 is supported by the source.')
    try:
        import uvicorn
        from server.app import create_app
        app=create_app()
    except ImportError as error:
        parser.exit(1,f'Missing package: {error.name}. Run this interpreter with -m pip install -r requirements.txt.\n')
    print(f'CrediBell: http://127.0.0.1:{args.port}/',flush=True)
    print('Anonymized sample images and PDFs. Press Ctrl+C to stop.',flush=True)
    import threading
    def warm():
        try: app.state.reader.warm()
        except Exception: pass  # Upload reports any reader error normally.
    threading.Thread(target=warm,daemon=True).start()
    if args.open:
        def open_browser():
            import time,urllib.request,webbrowser
            url=f'http://127.0.0.1:{args.port}/'
            for _ in range(100):
                try:
                    with urllib.request.urlopen(url+'api/health',timeout=.5) as response:
                        if response.status==200: webbrowser.open(url); return
                except OSError: time.sleep(.2)
        threading.Thread(target=open_browser,daemon=True).start()
    uvicorn.run(app,host='127.0.0.1',port=args.port,proxy_headers=False,access_log=False)

if __name__=='__main__': main()
