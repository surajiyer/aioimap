# aioimap: Asyncio IMAP client
Receive e-mails from an IMAP server asynchronously and trigger a callback with the message.

## Dependencies
aioimap requires:
* Python (>=3.7)
* aioimaplib (>=0.7.18)
* python-dotenv
* fastapi (>=0.61)
* uvicorn (>=0.12)

## Usage
Assume a project structure as so:  
```
project  
|  
|--app.py  
|--.env  
```

**app.py:**
```
from aioimap import Message

def callback(m: Message):
    print("Subject: {}".format(m.subject))
    print("Sender: {}".format(m.sender))
    # do some other fun stuff
```

**Terminal (without .env file):**
```
cd path/to/project
python -m aioimap --host <EMAILSERVER> -u <EMAILID> -p <PWD> -a "app:callback"
```

If you have a **.env** file in the same directory:
```
SERVER=<EMAILSERVER>
EMAIL=<EMAILID>
PASS=<PWD>
```

Then **Terminal (with .env file):**
```
cd path/to/project
python -m aioimap -a "app:callback"
```