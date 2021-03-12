import psutil
import time
import os
from shutil import copyfile
from datetime import datetime

DB_PATH = "./database.db"
BACKUP_FOLDER = './backup'

timestamp = None
if not os.path.exists(BACKUP_FOLDER):
    os.mkdir(BACKUP_FOLDER)


while True: #Infinite loop
    # закрытие мусорных процессов
    for proc in psutil.process_iter():
        try:
            # Get process name & pid from process object.
            processName = proc.name()
            processID = proc.pid
            if processName == 'www-browser' or processName == 'lynx':
                print(processName , ' ::: ', processID, ' will be killed')
                try:
                    proc.kill()
                except:
                    print('not killed, lol')
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    # backuper    
    date = datetime.now()
    if date != timestamp:
        dst_path = BACKUP_FOLDER + f"/database_{date.date()}.db"
        copyfile(DB_PATH, dst_path)
        print(f"Backup {dst_path} created")
        if len(os.listdir(BACKUP_FOLDER)) > 5:
            pass
        date = datetime.now()

    time.sleep(3600) #Wait 600s (10 min) before re-entering the cycle


