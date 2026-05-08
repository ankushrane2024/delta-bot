from flask import Flask, render_template, request, jsonify
from bot_core import bot_instance
import os

app = Flask(__name__, template_folder='.')

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/status', methods=['GET'])
def get_status():
    mode = request.args.get('mode', 'PAPER')
    return jsonify({
        'running': bot_instance.running,
        'running_mode': bot_instance.active_mode if bot_instance.running else None,
        'logs': bot_instance.get_logs(mode)
    })
    
@app.route('/api/state', methods=['GET'])
def get_state():
    mode = request.args.get('mode', 'PAPER')
    return jsonify(bot_instance.get_state(mode))

@app.route('/api/start', methods=['POST'])
def start_bot():
    data = request.json
    success = bot_instance.start(data)
    if success:
        return jsonify({'status': 'success', 'message': 'Engine initialized.'})
    return jsonify({'status': 'error', 'message': 'Engine is already running.'})

@app.route('/api/stop', methods=['POST'])
def stop_bot():
    success = bot_instance.stop()
    if success:
        return jsonify({'status': 'success', 'message': 'Engine halted.'})
    return jsonify({'status': 'error', 'message': 'Engine is not running.'})

@app.route('/api/execute', methods=['POST'])
def trigger_execution():
    if not bot_instance.running:
        return jsonify({'status': 'error', 'message': 'Please Initialize Engine first.'})
    bot_instance.trigger_execution()
    return jsonify({'status': 'success', 'message': 'Execution sweep triggered.'})

if __name__ == '__main__':
    os.makedirs('templates', exist_ok=True)
    app.run(debug=True, host='0.0.0.0', port=5000)
