import sys
import multiprocessing
from pathlib import Path


def main():
    multiprocessing.freeze_support()
    if '--screenshot' in sys.argv:
        import os
        target = Path(sys.argv[sys.argv.index('--screenshot') + 1]).resolve()
        os.environ.setdefault('MONTAGE_DATA_DIR', str(target.parent / (target.stem + '_diagnostic_data')))
    if len(sys.argv)>1:
        mode=sys.argv[1]
        if mode=='--transcribe':
            from montage.subtitles import transcribe
            transcribe(Path(sys.argv[2]),Path(sys.argv[3]),Path(sys.argv[4]),sys.argv[5],sys.argv[6])
            return 0
        if mode=='--separate':
            from montage.separation import separate
            separate(Path(sys.argv[2]),Path(sys.argv[3]),Path(sys.argv[4]))
            return 0
        if mode=='--run-batch':
            from montage.service import run_batch
            from montage.runtime import write_json
            result=run_batch(sys.argv[2],retry=True)
            if len(sys.argv)>3:
                write_json(Path(sys.argv[3]),result)
            return 1 if result['counts'].get('failed') else 0
        if mode=='--self-test':
            import os
            os.environ.setdefault('MONTAGE_DATA_DIR',str(Path(sys.argv[2]).resolve()/'diagnostic_data'))
            from montage.selftest import verify
            return verify(Path(sys.argv[2]))
        if mode=='--ui-test':
            import os
            os.environ.setdefault('MONTAGE_DATA_DIR',str(Path(sys.argv[2]).resolve()/'diagnostic_data'))
            from montage.uitest import verify
            return verify(Path(sys.argv[2]))
        if mode=='--cloud-test':
            import os
            os.environ.setdefault('MONTAGE_DATA_DIR',str(Path(sys.argv[2]).resolve()/'diagnostic_data'))
            from montage.cloudtest import verify
            return verify(Path(sys.argv[2]))
        if mode in ('--delivery-test','--stress-test'):
            import os
            os.environ.setdefault('MONTAGE_DATA_DIR',str(Path(sys.argv[2]).resolve()/'diagnostic_data'))
            from montage.deliverytest import extras,stress
            return (extras if mode=='--delivery-test' else stress)(Path(sys.argv[2]))
    from montage.gui import launch
    return launch(sys.argv)


if __name__=='__main__':
    try:
        raise SystemExit(main())
    except Exception:
        import traceback
        from montage.runtime import data_dir
        (data_dir()/'last_error.txt').write_text(traceback.format_exc(),encoding='utf-8')
        if getattr(sys,'frozen',False) and not any(x.startswith('--') for x in sys.argv[1:]):
            import ctypes
            ctypes.windll.user32.MessageBoxW(None,'启动或处理失败，详细信息保存在data/last_error.txt。','混剪工坊',0x10)
        raise
