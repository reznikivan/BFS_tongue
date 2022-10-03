from flask import Flask, render_template, Response
import time
import json
import sys
import traceback

import pickle

app = Flask(__name__)

@app.route('/')
def index():
    return(render_template('index.html'))

#Consumer API
@app.route('/topic/<topicname>')
def get_messages(topicname):
    def events():

        try:
            with open("shared.pkl", 'rb') as f:
                shared = pickle.load(f)
            print(type(shared))
            print('data:{0}\n\n'.format(json.dumps(shared)))
            yield 'data:{0}\n\n'.format(json.dumps(shared))
        except:
            
            print(traceback.format_exc())
        
    return Response(events(), mimetype="text/event-stream")

def Test():
    app.run(debug=True, host = "0.0.0.0", port = 5001)
#if __name__ == "__main__":
#    app.run(debug=True, host= "0.0.0.0", port=5001)
