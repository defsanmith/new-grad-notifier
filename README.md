# GitHub File Change Notifier

A production-ready Vercel serverless function that monitors GitHub repository file changes and sends email notifications via Gmail SMTP. Uses Vercel KV for persistent state storage and runs on cron schedules.

## Features

- 🔍 **GitHub API Integration**: Monitors specific files in public repositories
- 📧 **Gmail SMTP Notifications**: Sends HTML email alerts with commit details
- 💾 **Vercel KV Storage**: Persists last-seen commit SHA across serverless executions
- ⏰ **Cron Scheduling**: Configurable polling intervals via Vercel Cron Jobs
- 🔒 **Secure**: Uses environment variables for all credentials
- 📦 **Zero Dependencies**: Uses only Python standard library
- 🚀 **Production Ready**: Comprehensive error handling and JSON observability

## Quick Setup

### 1. Environment Variables

Add these environment variables in your Vercel project settings:

#### GitHub Configuration
```bash
GH_OWNER=SimplifyJobs              # Repository owner (default: SimplifyJobs)
GH_REPO=New-Grad-Positions         # Repository name (default: New-Grad-Positions)  
GH_BRANCH=dev                      # Branch to monitor (default: dev)
GH_TARGET_PATH=README.md           # File path to monitor (default: README.md)
GH_TOKEN=ghp_xxxxxxxxxxxx         # Optional: GitHub Personal Access Token
```

#### Vercel KV Configuration
```bash
KV_REST_API_URL=https://xxx.upstash.io    # Required: From Vercel KV dashboard
KV_REST_API_TOKEN=xxxxxxxxxxxx           # Required: From Vercel KV dashboard
STATE_KEY=custom-key                      # Optional: Custom state key
```

#### SMTP Configuration (Gmail)
```bash
SMTP_HOST=smtp.gmail.com           # SMTP server (default: smtp.gmail.com)
SMTP_PORT=587                      # SMTP port (default: 587)
SMTP_USER=your-email@gmail.com     # Required: Your Gmail address
SMTP_PASS=app-specific-password    # Required: Gmail App Password
MAIL_FROM=your-email@gmail.com     # From address (default: SMTP_USER)
MAIL_TO=notify@example.com,admin@example.com  # Required: Comma-separated recipients
```

### 2. Gmail App Password Setup

1. Enable 2-Factor Authentication on your Google account
2. Go to [Google App Passwords](https://myaccount.google.com/apppasswords)
3. Generate a new app password for "Mail"
4. Use the 16-character password as `SMTP_PASS`

### 3. Vercel KV Setup

1. In your Vercel project dashboard, go to **Storage** → **Create Database**
2. Select **KV (Upstash)**
3. Copy the `KV_REST_API_URL` and `KV_REST_API_TOKEN` to your environment variables

### 4. Deploy

```bash
# Clone this repository
git clone <your-repo-url>
cd new-grad-notifier

# Deploy to Vercel
npx vercel --prod

# Or connect via Vercel GitHub integration
```

### 5. Verify Cron Job

1. Go to your Vercel project dashboard
2. Navigate to **Settings** → **Functions**
3. Confirm the cron job is listed under **Cron Jobs**
4. Check **Function Logs** for execution results

## Configuration Options

### Custom State Key
By default, the state key format is: `{owner}/{repo}@{branch}:{path}`

Override with:
```bash
STATE_KEY=my-custom-project-key
```

### Polling Frequency
Edit `vercel.json` to change the cron schedule:

```json
{
  "crons": [
    {
      "path": "/api/watch_readme_notify.py", 
      "schedule": "0 */2 * * *"  // Every 2 hours
    }
  ]
}
```

### GitHub Rate Limits
- **Without token**: 60 requests/hour per IP
- **With token**: 5,000 requests/hour

Add `GH_TOKEN` for higher limits if needed.

## API Response Format

The function returns structured JSON for observability:

### Success - No Changes
```json
{
  "ok": true,
  "changed": false,
  "sha": "abc12345",
  "repo": "SimplifyJobs/New-Grad-Positions",
  "branch": "dev",
  "path": "README.md"
}
```

### Success - Changes Detected
```json
{
  "ok": true,
  "changed": true,
  "latest": "def67890",
  "new_commits": 3,
  "repo": "SimplifyJobs/New-Grad-Positions", 
  "branch": "dev",
  "path": "README.md"
}
```

### Error Response
```json
{
  "ok": false,
  "error": "SMTP not configured: MAIL_TO required"
}
```

## Email Format

Emails include:
- Repository and file information
- List of new commits with:
  - Short SHA (linked to GitHub)
  - Author name
  - First line of commit message
  - Direct link to commit

## Troubleshooting

### Check Function Logs
1. Go to Vercel Dashboard → Your Project → Functions
2. Click on `watch_readme_notify.py`
3. View execution logs and responses

### Common Issues

**"KV not configured"**
- Verify `KV_REST_API_URL` and `KV_REST_API_TOKEN` are set
- Ensure KV database is created in Vercel

**"SMTP not configured"**  
- Check `SMTP_USER`, `SMTP_PASS`, and `MAIL_TO` are set
- Verify Gmail App Password is correct (not regular password)

**"GitHub API error: 403"**
- Rate limit exceeded - add `GH_TOKEN` or reduce frequency
- Repository might be private (requires token)

**"No commits found"**
- File path might be incorrect
- Branch name might be wrong
- Repository might not exist or be accessible

### Manual Testing

Test the function directly:
```bash
curl https://your-project.vercel.app/api/watch_readme_notify.py
```

## File Structure

```
/
├── api/
│   └── watch_readme_notify.py  # Main serverless function
├── vercel.json                 # Cron job configuration  
└── README.md                   # This file
```

## Security Notes

- All credentials are stored as environment variables
- Gmail App Passwords provide secure SMTP access
- GitHub tokens are optional but recommended for private repos
- KV storage is isolated per Vercel project

## License

MIT License - feel free to adapt for your needs!
