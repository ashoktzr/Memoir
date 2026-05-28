# Design and Deployment of the Memoir Cloud-Based Journaling Platform

## Phase I — Application Development, Cloud Compute Provisioning, and Production Web Stack Initialization

## Abstract

This document details the full infrastructure engineering and deployment lifecycle of Memoir, a cloud-hosted personal journaling platform developed using Python and Flask. The project is structured in two progressive phases, each introducing new infrastructure layers while preserving the stability guarantees established in the previous phase.

Phase I establishes the foundational compute environment: an Amazon Linux–based EC2 instance running a minimal in-memory Flask application behind a production-grade Gunicorn + Nginx stack, managed as a persistent Linux service through systemd. The objective is to validate the entire request-processing pipeline — from public HTTP ingress through reverse proxy routing to WSGI application execution — before introducing any external persistence or application complexity.

Phase II extends this foundation with cloud-managed database persistence (AWS RDS MySQL), user authentication, content management features, a privacy-first data model, version control infrastructure, and single-click infrastructure automation using AWS Step Functions.

This staged methodology isolates infrastructure-level concerns from application-level concerns, reducing debugging complexity and enabling each layer to be validated independently.

---

## Introduction

Modern backend systems are no longer deployed as single-process applications directly exposed to the internet. Production-grade applications require layered infrastructure separation between request routing, application execution, process management, and persistent storage systems.

Memoir was designed not merely as a journaling platform, but as a practical implementation of real-world cloud deployment architecture using industry-standard backend engineering patterns. The project demonstrates the transition from a raw virtual machine to a fully automated, production-capable application stack — a process that mirrors the deployment workflows used across professional backend engineering environments.

The application stack combines:

* **Python** as the core programming language
* **Flask** as the web application framework
* **Gunicorn** as the WSGI application execution server
* **Nginx** as the reverse proxy and edge routing layer
* **systemd** for Linux process lifecycle management
* **AWS EC2** for cloud compute infrastructure
* **AWS RDS** for managed relational database persistence
* **AWS Step Functions** for infrastructure startup automation

The primary objective of Phase I was to establish a stable and production-capable compute environment capable of serving HTTP traffic reliably while maintaining process resilience and deployment isolation — using nothing more than a minimal in-memory Flask application as the validation payload.

---

## Application Architecture Overview

The deployed architecture follows a layered request-processing model, where each component is responsible for a single well-defined concern. Incoming client traffic never reaches the Python application directly; instead, it passes through multiple infrastructure layers that provide security, performance, and operational isolation.

```
                    ┌──────────────────────────────────┐
                    │       Public Internet Traffic     │
                    │       (HTTP on Port 80)           │
                    └───────────────┬──────────────────┘
                                    │
                                    ▼
                    ┌──────────────────────────────────┐
                    │    Nginx Reverse Proxy Layer      │
                    │                                   │
                    │  • Accepts all inbound HTTP       │
                    │  • Routes dynamic requests via    │
                    │    Unix socket to Gunicorn        │
                    │  • Serves /static and /favicon    │
                    │    directly from filesystem       │
                    │  • Handles error pages (5xx)      │
                    └───────────────┬──────────────────┘
                                    │
                          Unix Domain Socket
                       (app.sock, umask 007)
                                    │
                                    ▼
                    ┌──────────────────────────────────┐
                    │    Gunicorn WSGI Server           │
                    │                                   │
                    │  • 3 worker processes             │
                    │  • Pre-fork worker model          │
                    │  • Managed by systemd             │
                    │  • Error + access logging         │
                    └───────────────┬──────────────────┘
                                    │
                                    ▼
                    ┌──────────────────────────────────┐
                    │    Flask Application Runtime      │
                    │                                   │
                    │  • URL routing + view logic       │
                    │  • Jinja2 template rendering      │
                    │  • Session + authentication       │
                    │  • SQLAlchemy ORM queries         │
                    └───────────────┬──────────────────┘
                                    │
                                    ▼
                    ┌──────────────────────────────────┐
                    │  AWS RDS MySQL Database           │
                    │  (Phase II)                       │
                    │                                   │
                    │  • Managed persistence layer      │
                    │  • Accessible only from EC2       │
                    │    within same VPC                │
                    │  • Automated backups              │
                    └──────────────────────────────────┘
```

This layered separation introduces several critical operational advantages:

* **Security isolation** — The Python runtime is never exposed directly to the public internet. Nginx acts as a shield, accepting and filtering all inbound traffic before forwarding it internally.
* **Concurrent request processing** — Gunicorn manages multiple worker processes, enabling the application to serve simultaneous requests across available CPU cores.
* **Static asset efficiency** — Nginx serves CSS, JavaScript, images, and favicon files directly from the filesystem without invoking the Python application, significantly reducing application server load.
* **Fault isolation** — A crash in a single Gunicorn worker does not bring down the entire application. The master process automatically respawns failed workers.
* **Process resilience** — systemd ensures that both Nginx and Gunicorn start automatically on boot, restart after failure, and run as background daemons independent of any SSH session.
* **Infrastructure decoupling** — The database resides on a separate managed service (AWS RDS), making the compute layer stateless and independently replaceable.

Rather than exposing Flask directly to the internet using its built-in development server, the deployment adopts the same architectural principles commonly used in enterprise Python backend systems.

---

## Rationale Behind Technology Selection

### Python

Python was selected due to its extensive backend ecosystem, rapid development capabilities, readability, and strong compatibility with cloud-native tooling.

Its mature ecosystem provides stable integrations for:

* ORM systems (SQLAlchemy)
* Authentication frameworks (Flask-Login, Werkzeug)
* WSGI servers (Gunicorn)
* Cloud SDKs (Boto3)
* Database drivers (PyMySQL)
* Infrastructure automation

The language also allows rapid iteration while maintaining deployment flexibility across cloud environments.

---

### Flask Framework

Flask provides a lightweight web framework suitable for modular backend development.

The framework was chosen because it avoids unnecessary abstractions while still supporting:

* URL routing and view functions
* Jinja2 template rendering
* Session management and flash messaging
* Request/response handling
* ORM integration via Flask-SQLAlchemy
* Authentication systems via Flask-Login

Unlike larger frameworks such as Django, Flask allows direct visibility into deployment architecture and infrastructure interactions, making it ideal for understanding production deployment mechanics from the ground up.

---

### Gunicorn WSGI Server

Flask's built-in development server is not designed for production workloads. It lacks concurrency optimization, fault recovery, and process management capabilities.

Gunicorn was introduced as the Web Server Gateway Interface (WSGI) execution layer responsible for:

* Managing concurrent worker processes using a pre-fork model
* Executing Python application requests in isolated worker contexts
* Utilizing multiple CPU cores through parallel worker allocation
* Isolating individual worker failures from the master process
* Handling production request loads with configurable concurrency

Gunicorn acts as the bridge between Nginx and the Flask runtime environment. The worker allocation follows the commonly used formula:

```
Workers = (2 × CPU Cores) + 1
```

For a single-core `t3.micro` instance, this yields 3 workers — balancing concurrency with available CPU and memory resources.

---

### Nginx Reverse Proxy

Nginx operates as the external-facing edge server responsible for handling all public HTTP traffic.

Its responsibilities include:

* Receiving and accepting all incoming client connections on port 80
* Forwarding dynamic requests internally to Gunicorn via Unix domain socket
* Serving static assets (CSS, JavaScript, images) directly from the filesystem
* Handling error pages for upstream failures (502, 503, 504)
* Forwarding client identity headers (`X-Real-IP`, `X-Forwarded-For`) to the application
* Shielding backend processes from direct internet exposure

Nginx uses an asynchronous event-driven architecture capable of handling thousands of concurrent client connections with minimal memory overhead — making it significantly more efficient than thread-based servers for connection management.

---

### systemd Process Management

One of the most overlooked aspects of backend deployment is process lifecycle reliability.

Running Flask or Gunicorn manually inside an SSH session is operationally unstable because:

* Applications terminate when the SSH session disconnects
* Processes do not survive system reboots
* No automatic restart mechanism exists for crashed processes
* Logging becomes fragmented across terminal sessions
* Service ordering and dependencies become unmanaged

To solve this, systemd was integrated as the Linux service orchestration layer.

systemd enables:

* **Automatic startup** during server boot via `WantedBy=multi-user.target`
* **Background daemon execution** independent of any terminal session
* **Process monitoring and recovery** through configurable restart policies
* **Centralized runtime logging** through `journalctl`
* **Service ordering** to ensure dependencies start in the correct sequence

This transforms the application from a temporary terminal process into a continuously managed production service.

---

## AWS EC2 Infrastructure Provisioning

The compute layer was provisioned using an Amazon Linux–based AWS EC2 virtual machine instance in the `eu-north-1` (Stockholm) region.

Cloud compute provisioning included:

* Instance type selection (`t3.micro` — free tier eligible)
* Amazon Linux operating system image
* Security group configuration for controlled network access
* Key pair configuration for SSH authentication
* Public HTTP exposure for web traffic

The configured inbound security group rules were:

| Protocol | Port | Source    | Purpose                      |
| -------- | ---- | -------- | ---------------------------- |
| SSH      | 22   | Anywhere | Secure remote administration |
| HTTP     | 80   | Anywhere | Public web traffic           |

The separation of security rules ensures that SSH access remains restricted to trusted sources while HTTP traffic is publicly accessible for application serving.

![EC2 Instance — AWS Console](Screenshots/EC2_instance.png)

---

## Host Environment Initialization

After provisioning the EC2 instance, the operating system packages were synchronized and upgraded:

```bash
sudo yum update -y
```

Core runtime dependencies were installed:

```bash
sudo yum install python3 python3-pip gcc python3-devel nginx -y
```

These packages establish:

* Python 3 runtime execution
* Package installer for Python dependencies
* Python development headers for native extension compilation
* Nginx reverse proxy server
* GCC compiler for compiling gunicron like packages

The installation phase converts the raw Amazon Linux VM into a Python-capable backend host system ready for application deployment.

---

## Python Virtual Environment Isolation

Directly installing Python packages globally on the system can lead to dependency conflicts across applications and interfere with system-managed Python packages.

To isolate project dependencies, a dedicated Python virtual environment was created.

Project workspace initialization:

```bash
mkdir ~/myflask-proj
cd ~/myflask-proj
```

Virtual environment creation and activation:

```bash
python3 -m venv proj
source proj/bin/activate
```

Core backend dependencies installed within the isolated environment:

```bash
pip install flask gunicorn
```

The virtual environment ensures:

* **Dependency isolation** — Project packages do not conflict with system packages
* **Version consistency** — Package versions remain pinned regardless of system updates
* **Deployment portability** — The environment can be replicated on different machines
* **Reduced system contamination** — The base OS remains clean and unmodified

This mirrors production deployment standards used in professional backend infrastructure environments, where system Python is never used directly for application dependencies.

---

## Initial Flask Application Validation

Before integrating any external persistence systems, database connectivity, or application features, the Flask application was validated using a minimal in-memory implementation.

This initial version of the application was intentionally primitive:

* A basic home page route serving a simple HTML template
* A `/write` route for composing entries, accessible only by manually editing the browser address bar
* Posts stored entirely in a Python list within the application process — no database, no file storage
* No authentication, no user management, no sessions

The purpose of this stage was **not** to build application features, but to validate that the entire production request-processing pipeline was functioning correctly:

* HTTP requests reaching Nginx on port 80
* Nginx forwarding requests through the Unix socket to Gunicorn
* Gunicorn workers executing Flask application code
* Flask rendering templates and returning HTTP responses
* The full round-trip completing successfully from browser to server and back

This intermediate validation stage is critical because it isolates infrastructure-layer issues from application-layer complexity. If something fails at this stage, the problem is definitively in the Nginx → Gunicorn → Flask pipeline — not in database drivers, authentication logic, or ORM configuration.

---

## Production WSGI Deployment

After validating the application locally using Flask's built-in development server, Gunicorn was introduced as the production WSGI execution layer.

The application was initially tested using:

```bash
gunicorn --workers 3 app:app
```

This replaced Flask's single-threaded development server with a production-grade multi-process architecture capable of handling concurrent requests. Each Gunicorn worker operates as an independent process, isolating failures and improving resource utilization across CPU cores.

---

## Unix Socket Communication Architecture

Instead of exposing Gunicorn directly through a TCP port, communication between Nginx and Gunicorn was configured through a Unix domain socket:

```
/home/ec2-user/myflask-proj/app.sock
```

The socket file is created by Gunicorn with a umask of `007`, ensuring that only the owning user and group have access.

Unix socket communication provides:

* **Lower inter-process communication overhead** compared to TCP loopback
* **Faster local request forwarding** by eliminating network stack processing
* **Reduced attack surface** — no open TCP port for the application server
* **Improved security isolation** — access controlled through filesystem permissions

This architecture is the standard communication pattern used in production Linux web server environments where the reverse proxy and application server reside on the same host.

---

## Nginx Reverse Proxy Configuration

Nginx was configured as the edge routing layer, responsible for all public-facing HTTP traffic:

```nginx
server {
    listen 80;
    server_name _;

    location / {
        proxy_pass http://unix:/home/ec2-user/myflask-proj/app.sock;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }

    location /static {
        alias /home/ec2-user/myflask-proj/static;
    }

    location /favicon.ico {
        alias /home/ec2-user/myflask-proj/favicon.ico;
    }

    error_page 500 502 503 504 /500.html;
    location = /500.html {
        root /home/ec2-user/myflask-proj/templates;
    }
}
```

This configuration establishes:

* **Public HTTP listener** on port 80 for all incoming connections
* **Wildcard server name** (`server_name _`) — intentionally configured as a catch-all because an Elastic IP was not attached to the instance; the application is accessed directly via the instance's dynamic public IP address
* **Dynamic request proxying** — all application routes forwarded to Gunicorn through the Unix socket
* **Client identity forwarding** — `X-Real-IP` and `X-Forwarded-For` headers passed to the Flask application, enabling accurate client IP logging
* **Efficient static asset serving** — CSS, JavaScript, and image files served directly by Nginx without invoking the Python application
* **Favicon handling** — served directly from the project root
* **Error page routing** — upstream failures (502, 503, 504) display a custom error page rather than the default Nginx error response

The Flask application itself remains entirely inaccessible from the public internet. All traffic must pass through Nginx, which provides a controlled and auditable entry point.

The configuration file was placed in the Nginx sites-available directory and symlinked to sites-enabled:

```bash
sudo nano /etc/nginx/conf.d/memoir.conf
sudo nginx -t
sudo systemctl restart nginx
```

---

## systemd Service Integration

Gunicorn was registered as a persistent Linux service managed by systemd.

The initial service unit file for Phase I (before database integration):

```ini
[Unit]
Description=Gunicorn instance serving Memoir
After=network.target

[Service]
User=ec2-user
Group=nginx
WorkingDirectory=/home/ec2-user/myflask-proj
Environment="PATH=/home/ec2-user/myflask-proj/proj/bin"
ExecStart=/home/ec2-user/myflask-proj/proj/bin/gunicorn --workers 3 --bind unix:app.sock -m 007 app:app

[Install]
WantedBy=multi-user.target
```

Key configuration decisions:

* **`User=ec2-user`** — The application runs under the default Amazon Linux user account, not root
* **`Group=nginx`** — The Nginx group is used so that Nginx can read the Unix socket file created by Gunicorn
* **`WorkingDirectory`** — Ensures Gunicorn starts in the project directory where `app.py` resides
* **`Environment="PATH=..."`** — Points to the virtual environment's `bin` directory, ensuring the correct Python interpreter and installed packages are used
* **`--bind unix:app.sock -m 007`** — Binds to a Unix socket with restricted permissions
* **`WantedBy=multi-user.target`** — Ensures the service starts automatically during normal system boot

The service lifecycle was initialized using:

```bash
sudo systemctl daemon-reload
sudo systemctl enable gunicorn nginx
sudo systemctl start gunicorn nginx
```

At this stage, both Gunicorn and Nginx are enabled as persistent services that:

* **Start automatically** when the EC2 instance boots
* **Run as background daemons** independent of any SSH session
* **Restart automatically** after system reboots or service failures
* **Log runtime output** accessible through `journalctl -u gunicorn`

The application stack was now fully operational and serving HTTP traffic through the complete Nginx → Gunicorn → Flask pipeline. The in-memory dummy application was successfully accessible from a web browser via the instance's public IP address, validating the entire production infrastructure stack.

---

## Operational Outcomes of Phase I

The completion of this phase established a stable production-oriented backend environment with the following characteristics:

* Cloud-hosted Amazon Linux deployment on AWS EC2
* Reverse proxy architecture with Nginx edge routing
* Worker-based concurrent execution through Gunicorn WSGI
* Persistent service orchestration via systemd
* Dependency-isolated Python virtual environment
* Unix socket–based inter-process communication
* Automatic service startup on instance boot

The application stack was validated independently from any persistence systems, authentication logic, or application features — creating a stable and verified baseline for the next phase involving AWS RDS integration, user authentication, feature development, and infrastructure automation.

---
---

# Phase II — Cloud Database Integration, User Authentication, Feature Development, and Infrastructure Automation

## Introduction

With a stable compute and application execution environment established, the next infrastructure objective was the decoupling of persistent storage from the application server and the development of Memoir's full feature set.

In the initial validation stage, the Flask application relied on in-memory storage — posts existed only within the running Python process and were lost on every restart. While this served its purpose for infrastructure validation, it introduces fundamental limitations that make it unsuitable for any real application:

* **Data loss on restart** — All content disappears when Gunicorn workers restart or the instance reboots
* **No persistence guarantees** — There is no durable storage backing the application state
* **No multi-user support** — Without a database, user accounts and authentication are impossible
* **No scalability path** — In-memory state cannot be shared across multiple application instances

Beyond solving these immediate limitations, this phase was designed with a broader architectural vision: building Memoir as a **stateless application** that can eventually be horizontally scaled behind a load balancer. When the compute layer holds no persistent state, any number of application instances can serve traffic interchangeably — a foundational requirement for high-availability production systems.

This architectural direction also opens future enhancement paths such as Redis-based session caching (to externalize session state from individual instances), read replicas for database scaling, and auto-scaling groups for dynamic capacity management. While these enhancements remain in the pipeline for later phases, the infrastructure decisions made here were intentionally designed to support them.

The persistence layer was migrated into a dedicated managed relational database infrastructure using Amazon Web Services Relational Database Service (AWS RDS) with a MySQL engine. This phase transformed the architecture from a volatile in-memory prototype into a fully decoupled cloud-native infrastructure model.

---

## Why AWS RDS Was Selected

Managing databases manually on an EC2 instance introduces significant operational complexity that distracts from application development.

Self-managed database infrastructure requires responsibility for:

* Backup scheduling and retention
* Security patch management
* Replication and failover setup
* Disaster recovery operations
* Performance monitoring and tuning
* High availability configuration
* Storage capacity management

AWS RDS abstracts this entire operational burden into a managed platform.

The managed database service provides:

* **Automated backups** with configurable retention periods
* **Managed patch updates** applied during maintenance windows
* **Persistent EBS-backed storage** independent of instance lifecycle
* **Point-in-time recovery** through continuous backup streams
* **Monitoring integrations** via CloudWatch metrics
* **Multi-AZ replication support** for high availability configurations
* **Infrastructure reliability guarantees** backed by AWS SLAs

This allows engineering focus to remain on application development rather than low-level database administration — particularly important for a free-tier project where compute time is limited and every hour spent on infrastructure maintenance consumes billable resources.

---

## AWS RDS Provisioning

A dedicated MySQL-based RDS instance was provisioned within AWS in the `eu-north-1` (Stockholm) region.

| Configuration       | Value                   |
| ------------------- | ----------------------- |
| DB Identifier       | `flask-db`              |
| Engine              | MySQL Community         |
| Instance Class      | `db.t4g.micro`          |
| Region & AZ         | `eu-north-1b`           |
| Database Name       | `flask_blog`            |
| Port                | `3306`                  |

The database was deployed inside the same Virtual Private Cloud (VPC) as the EC2 instance to ensure low-latency internal communication and to avoid exposing database traffic to the public internet.

![RDS Instance — AWS Console](Screenshots/RDS_db_instance.png)

---

## Security Group and Network Configuration

Unlike in-memory storage, remote relational databases require explicit network-level authorization. The RDS instance was configured with a security group that restricts inbound traffic exclusively to the EC2 application server.

| Protocol  | Port | Source                     | Purpose                               |
| --------- | ---- | -------------------------- | ------------------------------------- |
| MySQL/TCP | 3306 | EC2 Security Group         | Application-to-database communication |

This architecture enforces a strict security boundary:

* The database is **not publicly accessible** — it has no public IP address
* Only traffic originating from the EC2 instance's security group is permitted
* All external clients, including developer machines, cannot connect directly to RDS
* Database administration is performed through the application or via SSH tunnel through EC2

The database remains invisible to the public internet and only accepts authenticated traffic from approved infrastructure sources within the same VPC.

---

## Flask Database Reconfiguration

The Flask application was reconfigured to connect to the remote RDS MySQL instance instead of using in-memory storage.

Environment-based configuration was introduced to keep credentials outside of source code:

```python
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-key-fallback')
```

This pattern provides several operational benefits:

* **Secrets remain outside source code** — Credentials are never committed to the repository
* **Infrastructure becomes portable** — The same codebase can connect to different databases by changing environment variables
* **Multiple deployment environments become possible** — Development, staging, and production can use different connection strings
* **Runtime configuration becomes flexible** — No code changes required to switch infrastructure targets

The `DATABASE_URL` environment variable follows the SQLAlchemy connection URI structure:

```
mysql+pymysql://USERNAME:PASSWORD@RDS-ENDPOINT:3306/DATABASE_NAME
```

The `pymysql` driver was installed as the MySQL connector:

```bash
pip install flask_sqlalchemy flask_login pymysql
```

---

## SQLAlchemy ORM Integration

The application uses Flask-SQLAlchemy as the Object Relational Mapping (ORM) layer, abstracting raw SQL interactions into Python object manipulation.

This enables:

* **Cleaner code structure** — Database operations expressed as Python method calls
* **Relationship management** — Foreign keys and joins handled through ORM abstractions
* **Query abstraction** — Filtering, ordering, and aggregation without writing raw SQL
* **Database portability** — The same ORM code works across SQLite, MySQL, PostgreSQL

The database models were defined as Python classes that map directly to relational database tables.

---

## Relational Database Schema Design

### User Entity

```python
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(256), nullable=False)
    posts = db.relationship('Post', backref='author', lazy=True)
```

The user table stores:

* **Unique identifiers** — Auto-incrementing primary key for each user
* **Login identity** — Unique username enforced at the database level
* **Authentication credentials** — Password hashes (never plaintext) using PBKDF2-SHA256
* **Relationship mapping** — One-to-many relationship with the Post entity

### Post Entity

```python
class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    content = db.Column(db.Text, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    is_public = db.Column(db.Boolean, default=False, nullable=False)
```

The post table establishes:

* **Referential integrity** — Foreign key constraint ensuring every post belongs to a valid user
* **Content storage** — Title and body text for journal entries
* **Privacy control** — `is_public` boolean flag defaulting to `False`, implementing a private-by-default content model

The `db.relationship('Post', backref='author', lazy=True)` declaration on the User model enables bidirectional navigation: `user.posts` returns all posts by a user, and `post.author` returns the owning user — without writing any SQL joins.

---

## User Authentication System

User authentication was implemented using Flask-Login for session management and Werkzeug's security utilities for password hashing.

### Password Security

Passwords are never stored in plaintext. The application uses PBKDF2-SHA256 hashing:

```python
# Registration — hash before storage
hashed_password = generate_password_hash(password, method='pbkdf2:sha256')

# Login — verify against stored hash
if check_password_hash(user.password, password):
    login_user(user)
```

This ensures that even if the database is compromised, user passwords remain cryptographically protected.

### Session Management

Flask-Login manages user sessions through secure cookies:

* `@login_required` decorator protects routes that require authentication
* `current_user` proxy provides access to the authenticated user in templates and routes
* `login_user()` and `logout_user()` handle session creation and destruction
* Unauthenticated users are automatically redirected to the login page

---

## Application Features

### Private Diary Dashboard

Authenticated users see their personal memory log on the home page — a private feed displaying only their own journal entries. Each entry shows its title, a truncated content preview, and a privacy badge indicating whether the entry is shared publicly or remains private.

### Public Sharing and Explore Feed

Users can optionally mark individual entries as public, making them visible on the **Shared Reflections** explore feed. This feed aggregates all public posts across the platform, displaying the post title, author attribution with a clickable profile link, and a content preview.

The sharing mechanism is intentionally one-directional: entries start private and can be explicitly made public through a dedicated action on the post detail page. This design ensures that no content is accidentally exposed.

### User Profile Pages

Each user has a public profile page (`/user/<username>`) that displays all of their publicly shared entries. This allows readers on the explore feed to discover more content from authors they find interesting.

### Post Management

Authenticated users can:

* **Create new entries** with a title, body content, and an optional public visibility toggle
* **View individual entries** on a dedicated detail page
* **Make private entries public** through a one-click action on the post detail page
* **Delete entries** with a confirmation prompt to prevent accidental data loss

![Memoir Application — Live Deployment](Screenshots/Memoir_index-html.png)

---

## Private-by-Default Privacy Architecture

The privacy model follows a **secure private-by-default** pattern:

* Every new journal entry is created with `is_public=False`
* Private entries are visible only to the authenticated author on their personal dashboard
* Public visibility requires an explicit opt-in action by the post owner
* The explore feed and user profile pages only display entries where `is_public=True`
* Authorization checks ensure that only the post owner can modify visibility or delete entries

This architecture ensures that personal journal content is never unintentionally exposed to other users or the public feed.

---

## Production Systemd Unit File Update

With the introduction of the database layer and application secrets, the systemd unit file required significant updates to inject environment variables into the Gunicorn runtime.

The updated service file:

```ini
[Unit]
Description=Gunicorn instance serving Memoir
After=network.target

[Service]
User=ec2-user
Group=nginx
WorkingDirectory=/home/ec2-user/myflask-proj
Environment="PATH=/home/ec2-user/myflask-proj/proj/bin"

# 🚀 PERSISTENT PRODUCTION CONFIGURATIONS
Environment="SECRET_KEY=<your-secret-key>"
Environment="DATABASE_URL=mysql+pymysql://<user>:<password>@flask-db.xxxxxx.eu-north-1.rds.amazonaws.com:3306/flask_blog"

ExecStart=/home/ec2-user/myflask-proj/proj/bin/gunicorn --workers 3 --bind unix:app.sock -m 007 app:app --error-logfile /home/ec2-user/myflask-proj/gunicorn.log --access-logfile /home/ec2-user/myflask-proj/access.log

[Install]
WantedBy=multi-user.target
```

Key additions compared to the Phase I unit file:

* **`SECRET_KEY`** — Flask session signing key injected as an environment variable rather than hardcoded in source
* **`DATABASE_URL`** — Full MySQL connection string injected at the systemd level, keeping credentials entirely outside the codebase
* **`--error-logfile`** — Gunicorn error output written to a dedicated log file for debugging
* **`--access-logfile`** — HTTP access logs captured for monitoring and audit purposes

This approach ensures that sensitive credentials exist only within the systemd service configuration on the EC2 instance and are never committed to version control.

![Gunicorn Systemd Unit File — Production Configuration](Screenshots/Gunicorn_unit-file.png)

After updating the unit file, the service was reloaded:

```bash
sudo systemctl daemon-reload
sudo systemctl restart gunicorn
```

---

## Version Control Infrastructure

Once the application architecture stabilized with database integration, user authentication, and content management features, version control infrastructure was introduced using Git.

### Why Git Was Introduced

Beyond the standard benefits of version control — code history tracking, rollback capability, and deployment reproducibility — Git served two specific operational purposes in this project:

* **Local development workflow** — With Git and a remote GitHub repository, application code can be modified and tested on a local development machine, then pushed to GitHub and pulled onto the EC2 instance. This eliminates the need to develop directly on the EC2 instance via SSH, which is both slower and more error-prone.

* **Free tier runtime conservation** — AWS free tier allocates a limited number of compute hours per month. By developing locally and only connecting to EC2 for deployment and testing, the instance can remain stopped when not actively serving traffic — significantly reducing free tier consumption.

The repository was initialized on the EC2 instance:

```bash
git init
git remote add origin https://github.com/<username>/memoir.git
```

---

### Repository Sanitization Through .gitignore

A `.gitignore` file was introduced to prevent accidental exposure of sensitive infrastructure artifacts and unnecessary files:

```
# Python Bytecode & Caches
__pycache__/
*.pyc
*.pyo
*.pyd
.pytest_cache/
.python-version

# Virtual Environments
proj/
venv/
env/
.venv/
ENV/

# Environment Variables & Secrets
.env
.flaskenv
*.secret
gunicorn.log
access.log

# Operating System Files
.DS_Store
Thumbs.db
*.swp
*~

# IDEs and Text Editors
.vscode/
.idea/
*.sublime-project
*.sublime-workspace

# Local Databases & Instance Folders
instance/
*.db
*.sqlite
*.sqlite3
```

This prevents committing:

* **Virtual environments** — Large dependency directories that should be recreated from requirements
* **Runtime logs** — Gunicorn error and access logs that contain operational data
* **Python cache files** — Compiled bytecode that is platform-specific
* **Environment secrets** — `.env` files that may contain database credentials or API keys
* **IDE configuration** — Editor-specific settings irrelevant to the application

Failure to properly sanitize repositories is one of the most common infrastructure security mistakes. If database credentials or secret keys are committed to a public repository, they can lead to infrastructure compromise, data theft, and unauthorized cloud resource abuse.

### Deployment Workflow

```bash
git add .
git commit -m "Integrated AWS RDS and privacy architecture"
git push -u origin main
```

Modern GitHub infrastructure requires Personal Access Tokens (PATs) for authenticated Git operations over HTTPS, replacing the deprecated password-based authentication.

---

## The Infrastructure Startup Problem

With both EC2 and RDS configured as stoppable resources (to conserve free tier usage), a critical operational dependency emerged.

The Gunicorn service is configured to start automatically when the EC2 instance boots (via `systemctl enable gunicorn`). However, the `DATABASE_URL` in the Gunicorn environment points to the RDS MySQL instance. If the EC2 instance starts **before** the RDS database is fully available, the following failure cascade occurs:

1. EC2 instance boots and systemd starts the Gunicorn service
2. Gunicorn spawns 3 worker processes
3. Each worker attempts to initialize the Flask application
4. Flask-SQLAlchemy tries to establish a connection to the RDS endpoint
5. The RDS instance is still starting up (status: `starting`, not `available`)
6. The connection attempt fails — **all 3 Gunicorn workers crash**
7. The application becomes unresponsive, requiring manual SSH intervention to restart Gunicorn after the database becomes available

This creates an unreliable startup sequence where the order of resource initialization matters critically. Manually starting the database first, waiting for it to become available, and then starting EC2 is tedious and error-prone.

---

## Solution: AWS Step Functions Infrastructure Automation

To solve the startup ordering problem, an AWS Step Functions state machine named **`Memoir_starter`** was created to orchestrate the entire infrastructure startup sequence with a single click.

The state machine implements the following workflow:

```
    ┌─────────────────────┐
    │       Start          │
    └──────────┬──────────┘
               │
               ▼
    ┌─────────────────────┐
    │  StartDBInstance     │
    │  (RDS: StartDB)     │
    └──────────┬──────────┘
               │
               ▼
    ┌─────────────────────┐
    │  Wait (60 seconds)  │
    └──────────┬──────────┘
               │
               ▼
    ┌─────────────────────┐
    │  GetDBStatus        │
    │  (RDS: DescribeDB)  │
    └──────────┬──────────┘
               │
               ▼
    ┌─────────────────────┐
    │  IsDBAvailable?     │◄──────┐
    │  (Choice State)     │       │
    └──────┬──────────────┘       │
           │                      │
     ┌─────┴─────┐          ┌────┴────┐
     │ Available  │          │ Default │
     ▼            │          │ (Wait)  │
    ┌─────────────┴───┐     └─────────┘
    │ StartEC2Instance │
    │ (EC2: StartInst) │
    └──────────┬──────┘
               │
               ▼
    ┌─────────────────────┐
    │        End          │
    └─────────────────────┘
```

The workflow logic:

1. **StartDBInstance** — Sends a `startDBInstance` API call to RDS for the `flask-db` instance
2. **Wait** — Pauses for 60 seconds to allow the database engine to begin initialization
3. **GetDBStatus** — Queries the current status of the RDS instance using `describeDBInstances`
4. **IsDBAvailable** — A Choice state that checks if `DbInstanceStatus` equals `"available"`
   * If **available** → proceed to start the EC2 instance
   * If **not available** → loop back to the Wait state and check again after another 60 seconds
5. **StartEC2Instance** — Once the database is confirmed available, starts the EC2 instance

This polling loop ensures that the EC2 instance — and therefore Gunicorn — only starts after the database is fully ready to accept connections.

### Step Function Definition (Amazon States Language)

```json
{
  "Comment": "Start RDS, wait for it to be available, then start EC2",
  "StartAt": "StartDBInstance",
  "States": {
    "StartDBInstance": {
      "Type": "Task",
      "Parameters": {
        "DbInstanceIdentifier": "flask-db"
      },
      "Resource": "arn:aws:states:::aws-sdk:rds:startDBInstance",
      "Next": "Wait"
    },
    "Wait": {
      "Type": "Wait",
      "Seconds": 60,
      "Next": "GetDBStatus"
    },
    "GetDBStatus": {
      "Type": "Task",
      "Parameters": {
        "DbInstanceIdentifier": "flask-db"
      },
      "Resource": "arn:aws:states:::aws-sdk:rds:describeDBInstances",
      "ResultPath": "$.dbInfo",
      "Next": "IsDBAvailable"
    },
    "IsDBAvailable": {
      "Type": "Choice",
      "Choices": [
        {
          "Variable": "$.dbInfo.DbInstances[0].DbInstanceStatus",
          "StringEquals": "available",
          "Next": "StartEC2Instance"
        }
      ],
      "Default": "Wait"
    },
    "StartEC2Instance": {
      "Type": "Task",
      "Parameters": {
        "InstanceIds": [
          "i-080922825bdd844a4"
        ]
      },
      "Resource": "arn:aws:states:::aws-sdk:ec2:startInstances",
      "End": true
    }
  }
}
```

![Step Function Workflow — Design View](Screenshots/Memoir_starter-step-function%20-graph.png)

---

### IAM Role and Least-Privilege Policy

The Step Functions state machine executes under a dedicated IAM service role: `StepFunctions-Memoir_starter-role-1uxxs0o9b`.

This role is attached to a custom-managed policy named `memoir_autostart-sf_policy` that follows the principle of **least privilege** — granting only the minimum permissions required for the state machine to function:

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "VisualEditor0",
            "Effect": "Allow",
            "Action": [
                "ec2:StartInstances",
                "rds:DescribeDBInstances",
                "rds:StartDBInstance"
            ],
            "Resource": [
                "arn:aws:rds:eu-north-1:549198689669:db:flask-db",
                "arn:aws:ec2:eu-north-1:549198689669:instance/i-080922825bdd844a4"
            ]
        }
    ]
}
```

Key security properties of this policy:

* **Action-scoped** — Only three specific API actions are permitted: starting EC2, starting RDS, and describing RDS status
* **Resource-scoped** — Permissions apply only to the specific RDS instance (`flask-db`) and EC2 instance (`i-080922825bdd844a4`), not to all resources in the account
* **No wildcard permissions** — No `*` in actions or resources, eliminating over-privileged access
* **Read-only where possible** — `rds:DescribeDBInstances` is read-only, used only to check database status

![IAM Role — Step Functions Service Role](Screenshots/IAM%20Role-Memoir-starter.png)

![IAM Policy — Least Privilege Permissions](Screenshots/Memoir_starter_role's_policy.png)

---

### Execution Results

The `Memoir_starter` state machine was executed successfully, completing the full startup sequence — from initiating the RDS instance to confirming database availability to starting the EC2 instance — in approximately **7 minutes** with 25 state transitions.

![Step Function Details](Screenshots/Memoir_starter_step-function.png)

![Step Function Execution — Succeeded](Screenshots/Memoir_starter_execution_scrnshot.png)

With this automation in place, the entire Memoir infrastructure can be brought online with a single click from the AWS Step Functions console — no SSH access, no manual sequencing, and no risk of Gunicorn worker crashes from premature database connections.

---

## Operational Outcomes of Phase II

The completion of this phase transformed Memoir from a volatile in-memory prototype into a fully featured, cloud-native, and operationally automated platform.

The system now supports:

* **Remote managed persistence** — All application data stored in AWS RDS MySQL, independent of EC2 lifecycle
* **User authentication** — Secure registration, login, and session management with hashed passwords
* **Content management** — Private journaling with optional public sharing and user profile pages
* **Privacy-first architecture** — Private-by-default content model with explicit opt-in public sharing
* **Infrastructure-independent storage** — The compute layer can be terminated, replaced, or scaled without data loss
* **Production logging** — Gunicorn error and access logs captured for debugging and monitoring
* **Version-controlled codebase** — Git-based workflow enabling local development and conserving free tier compute hours
* **Single-click infrastructure automation** — AWS Step Functions orchestrating the correct startup sequence for RDS and EC2
* **Least-privilege security** — IAM policies scoped to specific resources and actions

Most importantly, the application architecture now follows one of the most critical principles in distributed systems engineering:

> **Compute nodes should be disposable. Persistent data should not be.**

The EC2 instance can be stopped, terminated, or replaced at any time. The database persists independently. And when it's time to bring everything back online, a single Step Functions execution handles the entire orchestration — starting the database first, waiting for it to be ready, and only then starting the application server.
