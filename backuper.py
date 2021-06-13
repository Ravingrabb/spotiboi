import os
from shutil import copyfile
from datetime import datetime

DB_PATH = "./database.db"
BACKUP_FOLDER = './backup'

if not os.path.exists(BACKUP_FOLDER):
    os.mkdir(BACKUP_FOLDER)

date = datetime.now().date()
dst_path = BACKUP_FOLDER + f"/database_{date}.db"

copyfile(DB_PATH, dst_path)

if len(os.listdir(BACKUP_FOLDER)) > 5:
    pass

