# Local Development Setup for Enhanced GitHub App

This guide shows how to test the enhanced workflow tracing locally before deploying.

## What's Enhanced

The enhanced version creates **workflow-level transactions** that show:
- Total workflow duration
- Parent-child relationships between workflow and jobs
- Workflow-level metrics and tags
- Better visualization in Sentry

## Prerequisites

1. **ngrok** for local webhook testing
2. **Python 3.9+** with virtual environment
3. **Sentry DSN** for your project
4. **GitHub App** credentials

## Setup Steps

### 1. Install Dependencies

```bash
cd /Users/sergiolombana/Documents/sentry-gh-actions-app/sentry-github-actions-app
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
```

### 2. Configure Environment

Create `.env` file:
```bash
# GitHub App Configuration
GITHUB_APP_ID=your_app_id
GITHUB_APP_PRIVATE_KEY=your_private_key
GITHUB_WEBHOOK_SECRET=your_webhook_secret

# Sentry Configuration
SENTRY_DSN=your_sentry_dsn

# Development
LOGGING_LEVEL=INFO
FLASK_ENV=development
```

### 3. Start ngrok

```bash
ngrok http 5001
```

Note the ngrok URL (e.g., `https://abc123.ngrok.io`)

### 4. Configure GitHub Webhook

1. Go to your test repository settings
2. Add webhook with ngrok URL
3. Select "Workflow jobs" events
4. Content type: `application/json`

### 5. Start the Enhanced App

```bash
# Terminal 1: Start the app
source .venv/bin/activate
flask run -p 5001

# Terminal 2: Monitor logs
tail -f logs/app.log
```

## Testing the Enhanced Features

### 1. Test with Multi-Job Workflow

Use the existing test repository:
- https://github.com/sergio-playground/sentry-gh-actions-test

Run the "Multi-Job Test (MetaMask Style)" workflow.

### 2. What You'll See in Sentry

**Before (original app):**
```
frontend-tests     ████████████████████████████████████████
backend-tests      ████████████████████████████████████████
mobile-tests       ████████████████████████████████████████
security-scan      ████████████████████████████████████████
performance-tests  ████████████████████████████████████████
```

**After (enhanced app):**
```
workflow: Multi-Job Test (MetaMask Style) [186000ms total]
├─ frontend-tests [163000ms]
├─ backend-tests [135000ms] 
├─ mobile-tests [186000ms]
├─ security-scan [105000ms]
└─ performance-tests [169000ms]
```

### 3. Verify in Sentry

1. Go to your Sentry project
2. Navigate to Performance → Transactions
3. Look for:
   - `workflow: Multi-Job Test (MetaMask Style)` (parent)
   - `job: frontend-tests` (child)
   - `job: backend-tests` (child)
   - etc.

## Key Files Modified

- `src/web_app_handler.py` - Enhanced with WorkflowJobCollector
- `src/workflow_tracer.py` - New workflow-level tracing
- `test_enhanced_webhook.py` - Local testing script

## Troubleshooting

### Common Issues

1. **Import errors**: Make sure you're in the correct directory
2. **Webhook not receiving**: Check ngrok URL and GitHub webhook settings
3. **No traces in Sentry**: Verify DSN and check app logs

### Debug Commands

```bash
# Test webhook handler locally
python test_enhanced_webhook.py --no-dry-run

# Check app logs
tail -f logs/app.log

# Verify ngrok is running
curl https://abc123.ngrok.io/health
```

## Next Steps

1. **Test locally** with the setup above
2. **Verify traces** appear in Sentry with workflow hierarchy
3. **Deploy** to your environment
4. **Monitor** workflow performance in Sentry

## Benefits of Enhanced Version

- **Total workflow duration** visible in one place
- **Workflow-level performance metrics**
- **Clear parent-child relationships**
- **Better visualization** in Sentry's trace view
- **Workflow status aggregation** (success/failure/cancelled)

This gives you the MetaMask-style workflow visualization you wanted!



