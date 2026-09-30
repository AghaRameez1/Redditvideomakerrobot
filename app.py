#!/usr/bin/env python
"""Start Script Studio, then open http://127.0.0.1:5050"""
from backend import cleanup, create_app

if __name__ == "__main__":
    app = create_app()
    cleanup.start_scheduler(app)  # auto-clean of posted videos, if the admin turned it on
    # 127.0.0.1 only: the app runs tools on this machine, so it must not be reachable from the network.
    app.run(host="127.0.0.1", port=5050, debug=False, threaded=True)
