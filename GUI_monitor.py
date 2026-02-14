import tkinter as tk
from tkinter import ttk
import threading
import time
import requests
import sys
import os
import json
import ast

# Add project root to path so we can import database utils
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.append(project_root)
try:
    from database.utils.migrated_database_utils import create_database_service
except ImportError:
    print("Warning: Could not import database utils. DB stats will be unavailable.")
    create_database_service = None

POLL_INTERVAL = 10  # seconds (updated for real-time monitoring)

def create_rounded_rect(canvas, x1, y1, x2, y2, radius=25, **kwargs):
    points = [x1+radius, y1,
              x1+radius, y1,
              x2-radius, y1,
              x2-radius, y1,
              x2, y1,
              x2, y1+radius,
              x2, y1+radius,
              x2, y2-radius,
              x2, y2-radius,
              x2, y2,
              x2-radius, y2,
              x2-radius, y2,
              x1+radius, y2,
              x1+radius, y2,
              x1, y2,
              x1, y2-radius,
              x1, y2-radius,
              x1, y1+radius,
              x1, y1+radius,
              x1, y1]
    return canvas.create_polygon(points, **kwargs, smooth=True)

AGENTS = [
    {"name": "MCP Bus", "port": 8000, "endpoint": "/health"},
    {"name": "Chief Editor", "port": 8001, "endpoint": "/health"},
    {"name": "Scout (Deprecated)", "port": 8002, "endpoint": "/health", "deprecated": True},
    {"name": "Fact Checker (Verification)", "port": 8018, "endpoint": "/health"},
    {"name": "Analyst (Content Analysis)", "port": 8004, "endpoint": "/health"},
    {"name": "Synthesizer (Cluster Aggregation)", "port": 8005, "endpoint": "/health"},
    {"name": "Critic Agent", "port": 8006, "endpoint": "/health"},
    {"name": "Memory Agent (Storing data, Embeddings)", "port": 8007, "endpoint": "/health"},
    {"name": "Reasoning Agent", "port": 8008, "endpoint": "/health"},
    {"name": "Newsreader (Ingestion & Crawling)", "port": 8009, "endpoint": "/health"},
    {"name": "vLLM Service", "port": 8010, "endpoint": "/health"},
    {"name": "Analytics", "port": 8011, "endpoint": "/health"},
    {"name": "Archive", "port": 8012, "endpoint": "/health"},
    {"name": "GPU Orchestrator", "port": 8014, "endpoint": "/health"},
    {"name": "Crawler", "port": 8015, "endpoint": "/health"},
    {"name": "Journalist (Publishing)", "port": 8017, "endpoint": "/health"},
    {"name": "Workflow Orch (Job Scheduling)", "port": 8020, "endpoint": "/health"},
]

class StatusDashboard(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("JustNews System Status")
        self.geometry("700x800")
        self.minsize(500, 300)
        self.attributes('-topmost', True)
        style = ttk.Style(self)
        # Set dark theme: black background, white text, and double text size
        self.configure(bg="#111111")
        style.theme_use("clam")
        big_font = ("Helvetica", 13)  # Antialiased font
        heading_font = ("Helvetica", 13, "bold") # Matched to body size
        style.configure("Treeview",
                background="#111111",
                foreground="#ffffff",
                fieldbackground="#111111",
                borderwidth=0,
                rowheight=35,
                font=big_font)
        style.configure("Treeview.Heading",
                background="#222222",
                foreground="#ffffff",
                borderwidth=0,
                font=heading_font)
        style.map("Treeview",
              background=[('selected', '#333333')],
              foreground=[('selected', '#ffffff')])
        style.layout("Treeview", [('Treeview.treearea', {'sticky': 'nswe'})]) # Remove borders from layout if possible

        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.poll_interval = POLL_INTERVAL
        self.agent_rows = {}
        self.job_counts = {}
        self.last_job_counts = {}
        self.current_stats = {}
        self.create_widgets()
        self.polling = True
        self.poll_thread = threading.Thread(target=self.poll_loop, daemon=True)
        self.poll_thread.start()

    def create_widgets(self):
        # Create Status Icons
        self.icons = {}
        # Simple color squares generated in memory. Width increased to 30 to add padding between icon and text.
        for status, color in [("running", "#00AA00"), ("degraded", "#FFFF00"), ("stopped", "#FF5555"), ("deprecated", "#666666")]:
            img = tk.PhotoImage(width=30, height=14)
            img.put(color, to=(2, 2, 12, 12))
            self.icons[status] = img

        # Container Canvas for rounded border
        self.canvas = tk.Canvas(self, bg="#111111", highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # Frame to hold treeview (will be placed inside canvas)
        self.tree_frame = tk.Frame(self.canvas, bg="#111111")
        self.container_window = self.canvas.create_window(0, 0, window=self.tree_frame, anchor="nw")

        # --- NEW: Quick Stats Header ---
        self.stats_frame = tk.Frame(self.tree_frame, bg="#111111")
        self.stats_frame.pack(fill=tk.X, padx=10, pady=(10, 5))
        
        self.total_articles_label = tk.Label(self.stats_frame, text="Total Articles: -", bg="#111111", fg="#00FF00", font=("Helvetica", 12, "bold"))
        self.total_articles_label.pack(side=tk.LEFT, padx=10)
        
        self.last_ingest_label = tk.Label(self.stats_frame, text="Last Ingest: -", bg="#111111", fg="#FFFF00", font=("Helvetica", 11))
        self.last_ingest_label.pack(side=tk.RIGHT, padx=10)
        # -------------------------------

        self.tree = ttk.Treeview(self.tree_frame, columns=("Jobs", "Δ"), show="tree headings")
        self.tree.heading("#0", text="Component")
        self.tree.column("#0", width=420, anchor="w")
        
        self.tree.heading("Jobs", text="Outstanding Jobs")
        self.tree.column("Jobs", width=150, anchor="center")
        
        self.tree.heading("Δ", text="Δ Since Last")
        self.tree.column("Δ", width=100, anchor="center")
        
        self.tree.pack(fill=tk.BOTH, expand=True)

        # Configure hover highlighting
        self.tree.tag_configure("highlight", background="#333333")
        self.tree.bind("<Motion>", self.on_motion)
        self.tree.bind("<Leave>", self.on_leave)
        self.highlighted_item = None
        
        for agent in AGENTS:
            self.tree.insert("", "end", iid=agent["name"], text=agent["name"], image=self.icons["stopped"], values=("?", "?"))

        # Redraw Rounded Border on Resize
        self.canvas.bind("<Configure>", self.on_resize)

    def on_resize(self, event):
        w, h = event.width, event.height
        radius = 20
        self.canvas.delete("border")
        create_rounded_rect(self.canvas, 2, 2, w-2, h-2, radius, outline="#FF0000", width=2, fill="", tag="border")
        
        # Resize internal frame to fit inside border with padding
        pad = 8
        self.canvas.itemconfigure(self.container_window, width=w-2*pad, height=h-2*pad)
        self.canvas.coords(self.container_window, pad, pad)

    def on_motion(self, event):
        item = self.tree.identify_row(event.y)
        if item != self.highlighted_item:
            if self.highlighted_item:
                try:
                    self.tree.item(self.highlighted_item, tags=())
                except tk.TclError:
                    pass
            if item:
                try:
                    self.tree.item(item, tags=("highlight",))
                except tk.TclError:
                    pass
            self.highlighted_item = item

    def on_leave(self, event):
        if self.highlighted_item:
            try:
                self.tree.item(self.highlighted_item, tags=())
            except tk.TclError:
                pass
            self.highlighted_item = None

    def fetch_db_stats(self):
        stats = {}
        if not create_database_service:
            return stats
            
        try:
            db = create_database_service()
            conn = db.get_connection() 
            cursor = conn.cursor()

            # Newsreader Agent: Crawler Jobs
            try:
                cursor.execute("SELECT count(*) FROM crawler_jobs WHERE status IN ('pending', 'running')")
                stats["Newsreader (Ingestion & Crawling)"] = cursor.fetchone()[0]
            except Exception: pass

            # Crawl4AI: Active Crawls
            try:
                cursor.execute("SELECT count(*) FROM crawler_jobs WHERE status='running'")
                stats["Crawl4AI"] = cursor.fetchone()[0]
            except Exception: pass

            # Analyst Agent: Pending Analysis
            try:
                # Raw articles that haven't been analyzed yet
                cursor.execute("SELECT count(*) FROM articles WHERE analyzed=0 AND (is_synthesized=0 OR is_synthesized IS NULL)")
                stats["Analyst (Content Analysis)"] = cursor.fetchone()[0]
            except Exception: pass
            
            # Synthesizer: Remaining Clusters
            try:
                cursor.execute("SELECT id, input_cluster_ids FROM articles WHERE input_cluster_ids IS NOT NULL AND input_cluster_ids != '' AND input_cluster_ids != '[]'")
                rows = cursor.fetchall()
                all_clusters = set()
                for row in rows:
                    cluster_data = row[1]
                    try:
                        clusters = json.loads(cluster_data)
                    except:
                        try: clusters = ast.literal_eval(cluster_data)
                        except: continue
                    if isinstance(clusters, list):
                        for c in clusters: all_clusters.add(str(c))
                    elif isinstance(clusters, str):
                        all_clusters.add(clusters)
                
                cursor.execute("SELECT cluster_id FROM synthesized_articles")
                completed_rows = cursor.fetchall()
                completed = set(str(r[0]) for r in completed_rows)
                stats["Synthesizer (Cluster Aggregation)"] = len(all_clusters - completed)
            except Exception: pass

            # Fact Checker: Pending
            try:
                cursor.execute("SELECT count(*) FROM articles WHERE is_synthesized=1 AND (fact_check_status IS NULL OR fact_check_status='unknown')")
                stats["Fact Checker (Verification)"] = cursor.fetchone()[0]
            except Exception: pass
            
            # Publisher Agent: Pending
            try:
                cursor.execute("SELECT count(*) FROM articles WHERE is_synthesized=1 AND is_published=0")
                stats["Journalist (Publishing)"] = cursor.fetchone()[0]
            except Exception: pass

             # Workflow Orchestrator: Pending Jobs
            try:
                cursor.execute("SELECT count(*) FROM orchestrator_jobs WHERE status IN ('pending', 'running')")
                stats["Workflow Orch (Job Scheduling)"] = cursor.fetchone()[0]
            except Exception: pass
            
            # --- NEW: Global Article Stats ---
            try:
                cursor.execute("SELECT count(*) FROM articles")
                stats["_total_articles"] = cursor.fetchone()[0]
                cursor.execute("SELECT MAX(created_at) FROM articles")
                stats["_last_ingest"] = cursor.fetchone()[0]
            except Exception: pass

        except Exception as e:
            print(f"DB Poll Error: {e}")
        
        return stats

    def update_status(self):
        # Fetch DB stats once per update cycle
        self.current_stats = self.fetch_db_stats()

        # Update Header Labels
        total = self.current_stats.get("_total_articles", "?")
        last_ts = self.current_stats.get("_last_ingest", "Never")
        if last_ts and str(last_ts) != "None":
            # Format timestamp nicely if possible, else str
            pass 
        else:
             last_ts = "-"
        
        self.total_articles_label.config(text=f"Total Articles: {total}")
        self.last_ingest_label.config(text=f"Last Ingest: {last_ts}")

        for agent in AGENTS:
            name = agent["name"]
            port = agent["port"]
            endpoint = agent["endpoint"]
            
            if agent.get("deprecated"):
                 status = "deprecated"
            else:
                try:
                    resp = requests.get(f"http://localhost:{port}{endpoint}", timeout=3)
                    if resp.status_code == 200:
                        status = "running"
                    else:
                        status = "degraded"
                except Exception:
                    status = "stopped"
            
            jobs, delta = self.get_job_count(name)
            
            # Update row: Icon in #0, values in remaining columns
            self.tree.item(name, text=name, image=self.icons[status], values=(jobs, delta))

    def poll_loop(self):
        while self.polling:
            self.update_status()
            for _ in range(self.poll_interval):
                if not self.polling:
                    break
                time.sleep(1)

    def get_job_count(self, agent_name):
        current = self.current_stats.get(agent_name)
        
        if current is None:
            return "-", "-"
            
        prev = self.last_job_counts.get(agent_name, current)
        delta_val = current - prev
        self.last_job_counts[agent_name] = current
        
        delta_str = f"{'+' if delta_val > 0 else ''}{delta_val}" if delta_val != 0 else "-"
        return current, delta_str

    def on_close(self):
        self.polling = False
        self.destroy()

if __name__ == "__main__":
    app = StatusDashboard()
    app.mainloop()
