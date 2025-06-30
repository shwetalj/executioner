# Package Requirements Summary for Executioner Modernization

## Overview

This document summarizes the additional packages needed for the proposed modernization, organized by priority and implementation phase.

## Essential Packages by Implementation Phase

### Phase 1: Core Infrastructure (Weeks 1-2)
**Must Have:**
```txt
# Python 3.6 compatibility
dataclasses>=0.6; python_version < '3.7'
typing_extensions>=3.7.4

# Configuration Management
pydantic>=1.8.0,<2.0

# Testing Infrastructure
pytest>=6.0.0
pytest-cov>=2.10.0
pytest-mock>=3.3.0

# Code Quality
mypy>=0.910
black>=21.5b0
```

**Total: ~30MB installed**

### Phase 2: Database & Error Handling (Weeks 3-4)
**Must Have:**
```txt
# Database Abstraction
sqlalchemy>=1.3.0,<2.0

# Observability
structlog>=20.1.0
prometheus-client>=0.8.0
```

**Nice to Have:**
```txt
# PostgreSQL support
psycopg2-binary>=2.8.6

# Advanced monitoring
opentelemetry-api>=1.0.0
```

**Total: ~50MB additional**

### Phase 3: Async & API (Weeks 5-6)
**Must Have:**
```txt
# Async Support
aiofiles>=0.6.0
asyncio-throttle>=1.0.0

# API Framework
fastapi>=0.65.0
uvicorn>=0.13.0
httpx>=0.18.0
```

**Nice to Have:**
```txt
# Additional async support
aiohttp>=3.7.0
aiosqlite>=0.17.0
```

**Total: ~100MB additional**

## Minimal Implementation Package Set

If you want to start with the absolute minimum:

```txt
# requirements-minimal.txt
dataclasses>=0.6; python_version < '3.7'
typing_extensions>=3.7.4
pydantic>=1.8.0,<2.0
pytest>=6.0.0
mypy>=0.910
structlog>=20.1.0
```

**Total: ~20MB**

## Package Selection Rationale

### Why These Packages?

1. **Pydantic** - Industry standard for data validation, great Python 3.6 support
2. **SQLAlchemy** - Mature ORM with excellent abstraction capabilities
3. **FastAPI** - Modern but stable, built on standards, great docs
4. **Structlog** - Structured logging without breaking changes
5. **Pytest** - De facto standard for Python testing

### Packages We're NOT Using

1. **Django/Flask** - Too heavyweight for our needs
2. **Celery** - We have our own job queue system
3. **Redis** - Not needed for current scale
4. **Docker SDK** - Keeping deployment simple
5. **Heavy ML libraries** - Not relevant to our use case

## Installation Strategy

### 1. Create Virtual Environment
```bash
python3.6 -m venv venv
source venv/bin/activate
```

### 2. Install in Phases
```bash
# Phase 1: Core
pip install -r requirements-phase1.txt

# Phase 2: After core refactoring
pip install -r requirements-phase2.txt

# Phase 3: For async/API work
pip install -r requirements-phase3.txt
```

### 3. Development Dependencies
```bash
# Can be in separate file: requirements-dev.txt
pip install pre-commit tox coverage
```

## Size and Performance Impact

### Total Package Sizes (Approximate)
- **Current Executioner**: ~5MB (mostly stdlib)
- **Phase 1 Addition**: +30MB
- **Phase 2 Addition**: +50MB
- **Phase 3 Addition**: +100MB
- **Total with all features**: ~185MB

### Runtime Performance Impact
- **Memory**: +50-100MB RAM for full feature set
- **Startup Time**: +0.5-1s for all imports
- **Runtime Speed**: Generally faster due to optimized libraries

## Compatibility Matrix

| Package | Python 3.6 | Python 3.11 | Active Maintenance |
|---------|------------|--------------|-------------------|
| pydantic 1.x | ✅ | ✅ | ✅ (LTS) |
| SQLAlchemy 1.3+ | ✅ | ✅ | ✅ |
| FastAPI | ✅ | ✅ | ✅ |
| pytest 6.x | ✅ | ✅ | ✅ |
| structlog | ✅ | ✅ | ✅ |

## Risk Assessment

### Low Risk Packages
- pytest, mypy, black (development only)
- structlog, prometheus-client (simple APIs)
- pydantic 1.x (stable, no breaking changes)

### Medium Risk Packages
- SQLAlchemy (complex but stable)
- FastAPI (newer but stable API)

### Mitigation Strategies
1. Pin major versions in requirements.txt
2. Use `pip freeze` for production deployments
3. Test thoroughly on Python 3.6 and 3.11
4. Keep abstraction layers to swap packages if needed

## Recommendations

### For Conservative Implementation
Start with:
1. Basic type checking (mypy, typing_extensions)
2. Configuration validation (pydantic)
3. Structured logging (structlog)
4. Testing infrastructure (pytest)

### For Full Modernization
Add incrementally:
1. Database abstraction (SQLAlchemy)
2. Metrics (prometheus-client)
3. API layer (FastAPI)
4. Async support (aiofiles, asyncio packages)

### Package Update Policy
- Security updates: Apply immediately
- Minor updates: Test in dev first
- Major updates: Full regression testing
- Use dependabot or similar for monitoring

## Conclusion

The proposed packages add approximately 185MB to the installation size but provide:
- Type safety and validation
- Professional logging and monitoring
- Database abstraction
- Modern API capabilities
- Async execution support

All packages are well-maintained, support Python 3.6+, and are widely used in production environments.