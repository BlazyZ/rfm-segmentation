"""Windows local server; no reload process to avoid interrupting analysis tasks."""
import os
from rfm import create_app, service
from waitress import serve

app = create_app()

if __name__ == '__main__':
    service.recover_interrupted()
    host = os.getenv('APP_HOST', '127.0.0.1')
    port = int(os.getenv('APP_PORT', '5000'))
    print(f'零售客户分群系统：http://{host}:{port}', flush=True)
    serve(app, host=host, port=port, threads=6, max_request_body_size=app.config['MAX_CONTENT_LENGTH'])
