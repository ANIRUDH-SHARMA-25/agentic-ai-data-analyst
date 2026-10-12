"""Phase 3 HTTP API. Start with: python -m uvicorn backend.main:app."""

import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from backend.agent.analyst import AnalysisError, DataAnalysisAgent
from backend.config import APISettings
from backend.data.csv_processing import DatasetError, inspect_dataset, load_csv_bytes
from backend.data.dataset_manager import (
    DatasetCapacityError, DatasetManager, DatasetNotFoundError,
)
from backend.schemas import (
    AnalyzeRequest, AnalyzeResponse, DatasetResponse, ErrorResponse, HealthResponse, UploadResponse,
)
from backend.upload_limits import UploadBodyLimit


def create_app(
    settings: APISettings | None = None, *, manager: DatasetManager | None = None,
    analyzer: DataAnalysisAgent | None = None,
) -> FastAPI:
    settings = settings if settings is not None else APISettings.from_environment()
    manager = manager if manager is not None else DatasetManager(
        ttl_seconds=settings.dataset_ttl_seconds, max_datasets=settings.max_active_datasets,
    )

    analyzer = analyzer if analyzer is not None else DataAnalysisAgent()

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        # Starlette's multipart spool uses the process-wide tempfile directory.
        # This app runs in one process; keep transient upload files beside the repo.
        settings.temporary_directory.mkdir(parents=True, exist_ok=True)
        previous_directory = tempfile.tempdir
        tempfile.tempdir = str(settings.temporary_directory)
        try:
            yield
        finally:
            manager.clear()
            tempfile.tempdir = previous_directory

    application = FastAPI(title="Agentic AI Data Analyst", version="0.3.0", lifespan=lifespan)
    application.state.dataset_manager = manager
    application.state.settings = settings
    application.add_middleware(UploadBodyLimit, max_upload_bytes=settings.max_upload_bytes)

    @application.exception_handler(RequestValidationError)
    async def invalid_request(request, exception):
        return JSONResponse(
            {"detail": "Invalid request. Check required fields and parameter formats."},
            status_code=422,
        )

    @application.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse()

    def register_upload(payload: bytes, filename: str) -> UploadResponse:
        frame = load_csv_bytes(payload, filename=filename, max_bytes=settings.max_upload_bytes)
        summary = inspect_dataset(frame)
        # Inspection completes before consuming a session slot.
        dataset_id = manager.add(frame)
        return UploadResponse(
            dataset_id=dataset_id,
            **{key: summary[key] for key in ("row_count", "column_count", "columns", "dtypes", "preview")},
        )

    @application.post(
        "/upload", status_code=201, response_model=UploadResponse,
        responses={code: {"model": ErrorResponse} for code in (400, 413, 415, 422, 503)},
    )
    async def upload(file: Annotated[UploadFile, File(description="UTF-8 CSV dataset")]) -> UploadResponse:
        try:
            filename = file.filename or ""
            if (not filename or len(filename) > 255 or any(c in filename for c in '/\\:')
                    or any(ord(c) < 32 for c in filename)):
                raise HTTPException(400, "Upload filename must be a simple file name without a path.")
            if Path(filename).suffix.lower() != ".csv":
                raise HTTPException(415, "Only .csv files are supported.")
            payload = await file.read(settings.max_upload_bytes + 1)
            if len(payload) > settings.max_upload_bytes:
                raise HTTPException(413, f"CSV exceeds the {settings.max_upload_bytes}-byte size limit.")
            return await run_in_threadpool(register_upload, payload, filename)
        except DatasetError as exc:
            raise HTTPException(400, str(exc)) from exc
        except DatasetCapacityError as exc:
            raise HTTPException(503, str(exc)) from exc
        finally:
            await file.close()

    @application.get(
        "/dataset/{dataset_id}", response_model=DatasetResponse,
        responses={code: {"model": ErrorResponse} for code in (404, 422)},
    )
    def dataset_information(dataset_id: UUID) -> DatasetResponse:
        try:
            frame = manager.get(dataset_id)
        except DatasetNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        return DatasetResponse(dataset_id=dataset_id, **inspect_dataset(frame))

    @application.post(
        "/analyze", response_model=AnalyzeResponse,
        responses={code: {"model": ErrorResponse} for code in (404, 422, 429, 502, 503, 504)},
    )
    def analyze_dataset(request: AnalyzeRequest) -> AnalyzeResponse:
        try:
            frame = manager.get(request.dataset_id)
            return analyzer.analyze(frame, request.question)
        except DatasetNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except AnalysisError as exc:
            raise HTTPException(exc.status_code, str(exc)) from exc

    return application


app = create_app()
