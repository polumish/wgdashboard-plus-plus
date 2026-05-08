import dashboard
from datetime import datetime
global sqldb, cursor, DashboardConfig, WireguardConfigurations, AllPeerJobs, JobLogger, Dash
app_host, app_port = dashboard.gunicornConfig()
date = datetime.today().strftime('%Y_%m_%d_%H_%M_%S')

def post_worker_init(worker):
    dashboard.startThreads()
    dashboard.DashboardPlugins.startThreads()
    # Belt-and-suspenders: re-sync policy routing rules in the worker.
    # The primary sync_all() at dashboard.py module-level runs before
    # gunicorn attaches its file log handler, so any failure there is
    # invisible. Re-running here guarantees rules are applied and logged.
    try:
        with dashboard.app.app_context():
            dashboard.AllPolicyRouting.sync_all()
        dashboard.app.logger.info("[post_worker_init] PolicyRouting sync_all re-applied")
    except Exception as e:
        dashboard.app.logger.error(f"[post_worker_init] PolicyRouting sync_all failed: {e}", exc_info=True)

worker_class = 'gthread'
workers = 1
threads = 4
bind = f"{app_host}:{app_port}"
daemon = True
pidfile = './gunicorn.pid'
wsgi_app = "dashboard:app"
accesslog = f"./log/access_{date}.log"
loglevel = "info"
capture_output = True
errorlog = f"./log/error_{date}.log"
pythonpath = "., ./modules"

print(f"[Gunicorn] WGDashboard w/ Gunicorn will be running on {bind}", flush=True)
print(f"[Gunicorn] Access log file is at {accesslog}", flush=True)
print(f"[Gunicorn] Error log file is at {errorlog}", flush=True)
