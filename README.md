# Regbot
简单的Navidrome管理机器人

# Install 
1. git clone git@github.com:SenLief/Regbot.git
2. python -m venv .venv
3. source .venv/bin/activate
4. pip install -r requirements.txt

# Use
1. mv .env.example .env
2. modify .env file
3. python main.py

# Bot Use
- `/reg invitation_code,username,password`: Register users via invitation code
- `/reg username,password`: No invitation code required to register as a user
- `/deleteuser`: Delete user
- `/newinvite`: Generate invitation code[Admin]
- `/switch`：Turn off the invitation code system[Admin]
- `/adminreg username,password`：Register users via admin[Admin]
- `/deleteuser telegram_id`: Delete user via telegram_id[Admin]
