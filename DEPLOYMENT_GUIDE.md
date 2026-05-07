# Quick Deployment Guide - Voter Visibility & Evidence Signals

## What Changed

### Backend (Python/FastAPI)
- ✅ Fixed async/sync voter invocation (no more "coroutine was expected" errors)
- ✅ Added per-voter results with reasoning and metadata to API responses
- ✅ Added evidence reliability scores and page quality signals
- ✅ Proper UNCERTAIN classification (not lumped into plausible)
- ✅ All 89 tests passing locally

### Frontend (React)
- ✅ Updated `ClaimCard.jsx` to show voter analysis expandable section
- ✅ Updated `DetailPanel.jsx` to display full voter scorecard
- ✅ Evidence now shows reliability score and page quality signals
- ✅ Backward compatible with legacy API responses

## Pre-Deployment Checklist

- [ ] Pull latest code changes
- [ ] Run backend tests locally: `cd backend && pytest -q`
- [ ] Verify all 89 tests pass
- [ ] Check that frontend dependencies are up to date: `cd frontend && npm install`
- [ ] Build frontend: `npm run build`
- [ ] Start backend: `cd backend && python main.py` (or equivalent)
- [ ] Open frontend and run a test audit to verify voter results display

## API Response Structure

Every claim in the audit response now includes:

```javascript
{
  "label": "VERIFIED",        // New: official taxonomy label
  "voter_results": {          // New: per-voter analysis
    "heuristic_voter": {
      "status": "VERIFIED",
      "confidence": 0.88,
      "reasoning": "TF-IDF match on keywords...",
      "metadata": {...}       // Voter-specific signals
    }
  },
  "evidence": [{
    "reliability_score": 0.85,  // New: source reliability
    "page_quality_signals": {   // New: editorial quality metrics
      "editable_by_public": true,
      "editor_expertise_est": 0.75,
      "open_editability_score": 0.70
    }
  }],
  "runtime": {                // New: performance tracking
    "total_runtime_ms": 250.5,
    "retrieval_runtime_ms": 100.0,
    "voting_runtime_ms": 120.0,
    "num_urls": 2,
    "num_chunks": 5
  }
}
```

## Frontend Display Changes

### Claim Card
- **New Section**: "Show voter analysis" button reveals per-voter confidence and reasoning
- **Enhanced Evidence**: Reliability score badge and editorial quality indicators
- **Color-Coded Labels**: VERIFIED (green), PLAUSIBLE (yellow), REFUTED (red), UNCERTAIN (gray)

### Detail Panel
- **Voter Scorecard**: Full voter analysis with reasoning, metadata, and confidence bars
- **Evidence Quality**: Source reliability and page quality metrics displayed
- **Performance Metrics**: Runtime breakdown for retrieval vs voting phases

## Troubleshooting

### Issue: Voter section not showing
- **Check**: Audit API returns `voter_results` field (not just legacy `voter_scores`)
- **Fix**: Ensure backend is updated and restarted

### Issue: Evidence reliability showing as undefined
- **Check**: Audit API returns `reliability_score` in evidence objects
- **Fix**: Verify retrieval_router.py is using evidence construction with reliability signals

### Issue: "Coroutine was expected" errors in logs
- **Check**: orchestrator._run_cpu_voter() uses async/sync detection
- **Status**: This should be FIXED in this deployment

### Issue: UNCERTAIN claims still showing as PLAUSIBLE
- **Check**: Audit route is using `claim.label` (not `claim.status`) for counting
- **Fix**: Verify routes/audit.py has been updated

## Rollback Plan

If issues arise:
1. Revert backend code to previous commit
2. Revert frontend to previous build
3. Restart services
4. Monitor logs for "coroutine was expected" errors (indicates pre-fix code)

## Success Indicators

After deployment, verify:
- [ ] Audit endpoint returns 200 OK with voter_results in claims
- [ ] Frontend displays voter analysis section when clicking "Show voter analysis"
- [ ] Evidence cards show reliability score badges
- [ ] Page quality signals display in detail panel
- [ ] No "coroutine was expected" errors in backend logs
- [ ] UNCERTAIN claims are counted separately (check /audit response `uncertain` field)
- [ ] Runtime metrics shown in detail panel (retrieval_ms, voting_ms)

## Performance Expectations

- No change to response times (all signals computed during existing retrieval/voting)
- Slightly larger JSON response size (±5-10% due to voter metadata and signals)
- Frontend render time similar (additional fields but same DOM structure)

## Support Contact

For issues:
1. Check the logs for error messages
2. Verify all 89 tests pass locally
3. Compare current response structure to examples in VOTER_VISIBILITY_IMPLEMENTATION.md
4. Check that both backend and frontend were deployed
