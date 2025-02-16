from flask import Flask, render_template, request
from flask_socketio import SocketIO
import pty
import os
import subprocess
import select
import fcntl
import termios
import struct
import logging

app = Flask(__name__)
app.config['SECRET_KEY'] = os.urandom(24)
socketio = SocketIO(app)

app.config["fd"] = None
app.config["child_pid"] = None
app.config["cmd"] = ["/bin/bash"]


# this function is called when the terminal is connected
@socketio.on("connect", namespace="/pty")
def connect():
    # check if the file descriptor is set 
    if app.config["child_pid"]:
        # call the set_winsize function to resize the terminal
        return
    # create a new pty and fork the process
    (child_pid, fd) = pty.fork()

    if child_pid == 0:
        # change the working directory to the home directory
        home_directory = os.path.expanduser("~") 
        os.chdir(home_directory)
        subprocess.run(app.config["cmd"])
    else:
        app.config["fd"] = fd
        app.config["child_pid"] = child_pid
        set_winsize(fd, 50, 50)
        # start a background task to read the output from the pty and forward it to the client
        socketio.start_background_task(target=read_and_forward_pty_output)

def set_winsize(fd, row, col, xpix=0, ypix=0):
    winsize = struct.pack("HHHH", row, col, xpix, ypix)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, winsize)


@app.route("/terminal")
def terminal():
    return render_template("terminal.html")

@socketio.on("pty-input", namespace="/pty")
def pty_input(data):
    if app.config["fd"]:
        os.write(app.config["fd"], data["input"].encode())


def read_and_forward_pty_output():
    max_read_bytes = 1024 * 20
    
    while True:
        socketio.sleep(0.01)
        if app.config["fd"]:
            # check if there is any data to read from the pty
            timeout_sec = 0

            # select() will return when there is data to read from the pty in format (readable, _, _)   
            (data_ready, _, _) = select.select([app.config["fd"]], [], [], timeout_sec)

            # check if there is data to read from the pty and read it
            if data_ready:
                output = os.read(app.config["fd"], max_read_bytes).decode(errors="ignore")

                socketio.emit("pty-output", {"output": output}, namespace="/pty")


@socketio.on("resize", namespace="/pty")
def resize(data):
    if app.config["fd"]:
        set_winsize(app.config["fd"], data["rows"], data["cols"])



if __name__ == "__main__":
    # set the log level to debug
    logging.basicConfig(level=logging.DEBUG)
    socketio.run(app, debug=True, port=5000)
