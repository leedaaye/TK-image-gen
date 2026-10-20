Option Explicit
Dim shell, fs, root, python, args, arg
Set shell = CreateObject("WScript.Shell")
Set fs = CreateObject("Scripting.FileSystemObject")
root = fs.GetParentFolderName(WScript.ScriptFullName)
python = root & "\.venv\Scripts\pythonw.exe"
If Not fs.FileExists(python) Then python = "pythonw.exe"
args = ""
For Each arg In WScript.Arguments
  If arg = "--stop" Or arg = "--setup" Or arg = "--rebuild" Then args = args & " " & arg
Next
shell.CurrentDirectory = root
On Error Resume Next
shell.Run Chr(34) & python & Chr(34) & " " & Chr(34) & root & "\scripts\launcher.py" & Chr(34) & args, 0, False
If Err.Number <> 0 Then MsgBox "Python 3.11+ is required. Install Python with PATH enabled, then retry.", 16, "TK Studio"
