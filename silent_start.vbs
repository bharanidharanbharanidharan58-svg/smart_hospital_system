Set objShell = CreateObject("WScript.Shell")
objShell.CurrentDirectory = "C:\Users\bhara\.gemini\antigravity\scratch\smart_hospital_system"
objShell.Run "C:\Users\bhara\.local\bin\uv.exe run --with werkzeug --with flask app.py", 0, False