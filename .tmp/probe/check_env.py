import os, sys; sys.path[:0] = ['.']; print('CWD=', os.getcwd()); print('DATABASE_URL=', repr(os.environ.get('DATABASE_URL'))); print('SECRET_KEY=', repr(os.environ.get('SECRET_KEY')))
