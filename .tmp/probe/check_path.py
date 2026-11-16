import os
import sys
print('CWD=', os.getcwd())
print('argv0=', sys.argv[0])
print('path0=', sys.path[:5])
print('cwd_in_path=', os.getcwd() in sys.path)

