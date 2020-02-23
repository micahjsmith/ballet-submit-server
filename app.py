from flask import Flask, request
from flask_cors import CORS

app = Flask(__name__)
CORS(app)


@app.route('/status')
def status():
    return 'OK'


@app.route('/hello', methods=['POST'])
def hello():
    data = request.json
    print(data)
    return 'hello'
