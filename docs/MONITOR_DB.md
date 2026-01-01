# Monitor Zana Database from Your Laptop

This guide shows you how to access and monitor the Zana SQLite database from your laptop (WSL or Windows) using SSH port forwarding.

## Quick Start

### Step 1: Start Monitoring Container on VM

SSH into your GCP VM and start the monitoring container:

```bash
# SSH into VM
gcloud compute ssh vm-telegram-bots

# Navigate to project directory
cd /opt/zana-bot

# Start monitoring container
sudo docker compose up -d zana-db-monitor

# Verify it's running
sudo docker compose ps | grep db-monitor
```

Expected output:
```
zana-db-monitor   Up   127.0.0.1:8081->8081/tcp
```

---

### Step 2: Set Up SSH Port Forwarding from Your Laptop

#### Option A: WSL (Windows Subsystem for Linux)

Open WSL terminal and run:

```bash
# Forward the database monitoring port
gcloud compute ssh vm-telegram-bots -- -L 8081:127.0.0.1:8081
```

**Keep this terminal open** - the SSH tunnel stays active while this command runs.

#### Option B: Windows PowerShell

Open PowerShell and run:

```powershell
# Forward the database monitoring port
gcloud compute ssh vm-telegram-bots -- -L 8081:127.0.0.1:8081
```

**Keep this PowerShell window open** - the SSH tunnel stays active while this command runs.

---

### Step 3: Access the Database UI

Once the SSH tunnel is active, open your browser:

**http://localhost:8081**

You should see the sqlite-web interface showing both databases:
- **production.db** - Production database
- **staging.db** - Staging database

Click on either database to browse its tables and data.

---

## Detailed Instructions

### What This Setup Does

1. **On the VM**: One lightweight `sqlite-web` container runs in read-only mode
   - Port 8081, serving both databases:
     - Production: `/srv/zana-users/zana.db` (accessible as `production.db`)
     - Staging: `/srv/zana-users-staging/zana.db` (accessible as `staging.db`)
   - The interface shows both databases for selection

2. **On Your Laptop**: SSH port forwarding creates a secure tunnel
   - `localhost:8081` → VM's `127.0.0.1:8081`

3. **Security**: 
   - Containers bind to `127.0.0.1` only (not publicly accessible)
   - Database access is read-only
   - All traffic encrypted through SSH tunnel
   - No firewall rules needed

---

## Accessing Specific Databases

The single container serves both databases. When you open http://localhost:8081, you'll see a list of available databases:
- **production.db** - Click to view production database
- **staging.db** - Click to view staging database

Simply click on the database you want to explore.

---

## Convenience Aliases (Optional)

### WSL

Add to your `~/.bashrc` or `~/.zshrc`:

```bash
alias zana-db="gcloud compute ssh vm-telegram-bots -- -L 8081:127.0.0.1:8081"
```

Then reload: `source ~/.bashrc` (or `source ~/.zshrc`)

Usage:
```bash
zana-db    # Forward database monitoring port
```

### Windows PowerShell

Add to your PowerShell profile (`$PROFILE`):

```powershell
function Connect-ZanaDB {
    gcloud compute ssh vm-telegram-bots -- -L 8081:127.0.0.1:8081
}
```

Usage:
```powershell
Connect-ZanaDB    # Forward database monitoring port
```

---

## Troubleshooting

### Issue: "Connection refused" when accessing localhost:8081

**Possible causes:**

1. **Monitoring container not running on VM**
   ```bash
   # SSH into VM and check
   gcloud compute ssh vm-telegram-bots
   sudo docker compose ps | grep db-monitor
   
   # If not running, start it
   cd /opt/zana-bot
   sudo docker compose up -d zana-db-monitor
   ```

2. **SSH tunnel not active**
   - Make sure the `gcloud compute ssh` command is still running
   - Check that you didn't close the terminal/PowerShell window
   - Restart the SSH tunnel

3. **Port already in use on your laptop**
   ```bash
   # WSL: Check what's using the port
   sudo lsof -i :8081
   
   # Windows PowerShell: Check what's using the port
   netstat -ano | findstr :8081
   ```
   
   If something else is using the port, either:
   - Stop the conflicting service
   - Use a different local port (change `8081` to `9081` in the SSH command, and update the container port mapping)

### Issue: "Cannot connect to Docker daemon" on VM

```bash
# Check Docker status
sudo systemctl status docker

# Start Docker if needed
sudo systemctl start docker
```

### Issue: Database file not found

```bash
# SSH into VM and verify database exists
gcloud compute ssh vm-telegram-bots

# Check staging database
ls -lh /srv/zana-users-staging/zana.db

# Check production database
ls -lh /srv/zana-users/zana.db
```

If the database doesn't exist, the container will fail to start. Check container logs:

```bash
sudo docker compose logs zana-db-monitor
```

### Issue: "Permission denied" when accessing database

The containers mount the database directories as read-only (`:ro`), but the directories themselves need to be readable. Check permissions:

```bash
# On VM
ls -ld /srv/zana-users
ls -ld /srv/zana-users-staging

# If needed, fix permissions (be careful in production!)
sudo chmod 755 /srv/zana-users
sudo chmod 755 /srv/zana-users-staging
```

### Issue: SSH connection drops frequently

Add keep-alive options to your SSH command:

```bash
gcloud compute ssh vm-telegram-bots -- \
  -o ServerAliveInterval=60 \
  -o ServerAliveCountMax=3 \
  -L 8081:127.0.0.1:8081
```

Or add to your SSH config (`~/.ssh/config`):

```
Host vm-telegram-bots
  ServerAliveInterval 60
  ServerAliveCountMax 3
```

---

## Managing Monitoring Containers

### Start Container

```bash
# On VM
cd /opt/zana-bot
sudo docker compose up -d zana-db-monitor
```

### Stop Container

```bash
# On VM
sudo docker compose stop zana-db-monitor
```

### View Logs

```bash
# On VM
sudo docker compose logs -f zana-db-monitor
```

### Restart Container

```bash
# On VM
sudo docker compose restart zana-db-monitor
```

### Check Container Status

```bash
# On VM
sudo docker compose ps | grep db-monitor
```

---

## Security Notes

### Why This Is Secure

1. **No Public Exposure**: Containers bind to `127.0.0.1` only, not `0.0.0.0`
   - This means they're only accessible from the VM itself
   - Not reachable from the internet

2. **SSH Encryption**: All traffic between your laptop and VM is encrypted
   - Uses the same security as your regular SSH access
   - No additional firewall rules needed

3. **Read-Only Access**: Database is mounted read-only (`:ro`)
   - Prevents accidental modifications
   - sqlite-web runs with `-x` flag (read-only mode)

4. **Local Access Only**: Port forwarding only works from your laptop
   - Other users cannot access your forwarded ports
   - Each SSH session creates its own tunnel

### Best Practices

- **Don't leave SSH tunnels open unnecessarily** - Close them when done
- **Use read-only mode** - Already configured, but don't change it
- **Monitor access** - Check VM logs if you notice unusual activity
- **Keep gcloud CLI updated** - For security patches

---

## Alternative: Using Regular SSH (if gcloud CLI not available)

If you don't have `gcloud` CLI set up, you can use regular SSH:

```bash
# First, get the VM's external IP
gcloud compute instances describe vm-telegram-bots --format='get(networkInterfaces[0].accessConfigs[0].natIP)'

# Then use regular SSH with port forwarding
ssh -L 8081:127.0.0.1:8081 your-username@VM_EXTERNAL_IP
```

Replace `your-username` and `VM_EXTERNAL_IP` with your actual values.

---

## Quick Reference

| Task | Command |
|------|---------|
| Start monitoring container | `sudo docker compose up -d zana-db-monitor` |
| Forward database port | `gcloud compute ssh vm-telegram-bots -- -L 8081:127.0.0.1:8081` |
| Access database UI | http://localhost:8081 |
| Check container status | `sudo docker compose ps \| grep db-monitor` |
| View container logs | `sudo docker compose logs -f zana-db-monitor` |

---

## Need Help?

If you encounter issues not covered here:

1. Check container logs on the VM
2. Verify database files exist and are readable
3. Ensure SSH tunnel is active (terminal/PowerShell still running)
4. Try restarting the monitoring containers
5. Check Docker daemon is running on VM

