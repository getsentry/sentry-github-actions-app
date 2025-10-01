# 🚀 Implement Hierarchical Workflow Tracing with Single Transaction Structure

## 📋 Summary

This PR transforms the GitHub Actions workflow tracing from individual job transactions to a single workflow transaction containing nested job and step spans, providing better visibility into workflow timing and structure.

## 🎯 Problem Solved

**Before**: Individual job transactions created a flat structure in Sentry, making it difficult to understand workflow timing and relationships.

**After**: Single workflow transaction with proper hierarchical spans showing:
- Workflow-level timing and status
- Individual job spans as children
- Step spans as children of their respective jobs

## 🔧 Key Changes

### Core Implementation
- **`WorkflowTracer`**: New class for creating single workflow transactions with nested spans
- **`WorkflowJobCollector`**: Collects jobs from workflow runs and sends workflow-level traces
- **Enhanced `WebAppHandler`**: Integrates job collection and workflow tracing

### Sentry Payload Fixes
- ✅ Removed `event_id` from transaction payload (handled in envelope headers)
- ✅ Fixed timestamp format (removed `+00:00` UTC offset)
- ✅ Corrected status mapping for skipped jobs (`"ok"` instead of `"internal_error"`)
- ✅ Added required `sdk` field with name and version
- ✅ Added `trace_version` tags for validation

### Architecture Improvements
- ✅ Disabled individual job transactions to prevent duplicates
- ✅ Disabled Flask automatic Sentry tracing to prevent interference
- ✅ Added thread-safe job collection with race condition prevention
- ✅ Implemented proper span hierarchy: `workflow -> jobs -> steps`

## 📊 Trace Structure

**New Structure**:
```
workflow: Multi-Job Test (transaction)
├─ security-scan (job span)
│  ├─ Set up job (step span)
│  ├─ Checkout code (step span)
│  └─ Run security scan (step span)
├─ performance-tests (job span)
│  ├─ Set up job (step span)
│  ├─ Setup performance test environment (step span)
│  └─ Run performance tests (step span)
└─ backend-tests (job span)
   ├─ Set up job (step span)
   ├─ Setup Python (step span)
   └─ Run backend unit tests (step span)
```

## 🧪 Testing

- ✅ Local testing with mock data
- ✅ Real GitHub workflow testing
- ✅ Sentry payload validation
- ✅ Trace structure verification
- ✅ Performance impact assessment

## 📁 Files Changed

- `src/workflow_tracer.py` - New WorkflowTracer implementation
- `src/web_app_handler.py` - Enhanced with WorkflowJobCollector
- `src/main.py` - Disabled Flask automatic Sentry tracing
- `src/github_sdk.py` - Disabled individual job traces
- `src/enhanced_web_app_handler.py` - Alternative handler implementation
- `LOCAL_DEVELOPMENT.md` - Development setup guide
- `TESTING_SUMMARY.md` - Testing documentation

## 🔍 Validation

The implementation includes `trace_version: v3.6` tags for easy validation that traces are coming from the updated code.

## 🚀 Benefits

1. **Better Visibility**: Single workflow transaction shows complete timing
2. **Proper Hierarchy**: Clear parent-child relationships between workflow, jobs, and steps
3. **Reduced Noise**: Eliminates duplicate individual job transactions
4. **Improved Debugging**: Easier to identify workflow bottlenecks and issues
5. **Sentry Compliance**: Proper payload structure that Sentry processes correctly

## ⚠️ Breaking Changes

- Individual job transactions are no longer sent
- Trace structure is completely different (hierarchical vs flat)
- Requires Sentry project configuration update for proper visualization

## 🔄 Migration

Existing traces will continue to work. New traces will use the hierarchical structure. The `trace_version` tag helps identify which version generated each trace.


