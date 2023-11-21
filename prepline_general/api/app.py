from fastapi import FastAPI, Request, status, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel, Field
from typing import List
import logging
import os

from .general import router as general_router

logger = logging.getLogger("unstructured_api")


app = FastAPI(
    title="Unstructured Pipeline API",
    summary="Partition documents with the Unstructured library",
    version="0.0.57",
    docs_url="/general/docs",
    openapi_url="/general/openapi.json",
    servers=[
        {
            "url": "https://api.unstructured.io",
            "description": "Hosted API",
            "x-speakeasy-server-id": "prod"
        },
        {
            "url": "http://localhost:8000",
            "description": "Development server",
            "x-speakeasy-server-id": "local"
        }
    ],
    openapi_tags=[{"name": "general"}],
)

# Note(austin) - This logger just dumps exceptions
# We'd rather handle those below, so disable this in deployments
uvicorn_logger = logging.getLogger("uvicorn.error")
if os.environ.get("ENV") in ["dev", "prod"]:
    uvicorn_logger.disabled = True


# Catch all HTTPException for uniform logging and response
@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, e: HTTPException):
    logger.error(e.detail)
    return JSONResponse(status_code=e.status_code, content={"detail": e.detail})


# Catch any other errors and return as 500
@app.exception_handler(Exception)
async def error_handler(request: Request, e: Exception):
    return JSONResponse(status_code=500, content={"detail": str(e)})


allowed_origins = os.environ.get("ALLOWED_ORIGINS", None)
if allowed_origins:
    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins.split(","),
        allow_methods=["OPTIONS", "POST"],
        allow_headers=["Content-Type"],
    )

app.include_router(general_router)


# Filter out /healthcheck noise
class HealthCheckFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.getMessage().find("/healthcheck") == -1


# Filter out /metrics noise
class MetricsCheckFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.getMessage().find("/metrics") == -1


logging.getLogger("uvicorn.access").addFilter(HealthCheckFilter())
logging.getLogger("uvicorn.access").addFilter(MetricsCheckFilter())


@app.get("/healthcheck", status_code=status.HTTP_200_OK, include_in_schema=False,)
def healthcheck(request: Request):
    return {"healthcheck": "HEALTHCHECK STATUS: EVERYTHING OK!"}

# OpenAPI spec customizations
def custom_openapi():
    if app.openapi_schema:
        return app.openapi_schema

    openapi_schema = get_openapi(
        title=app.title,
        version=app.version,
        summary=app.summary,
        description=app.description,
        servers=app.servers,
        routes=app.routes,
        tags=app.openapi_tags,
        
    )

    # Add security
    openapi_schema["security"] = [{"ApiKeyAuth":[]}]

    # Add retries
    openapi_schema["x-speakeasy-retries"] = {
        "strategy": "backoff",
        "backoff": {
            "initialInterval": 500,
            "maxInterval": 60000,
            "maxElapsedTime": 3600000,
            "exponent": 1.5,
        },
        "statusCodes": [
            "5xx",
        ],
        "retryConnectionErrors": True,
    }

    # Path changes
    # Update the $ref in paths
    openapi_schema["paths"]["/general/v0/general"]["post"]["requestBody"]["content"]["multipart/form-data"]["schema"]["$ref"] = "#/components/schemas/partition_parameters"
    openapi_schema["paths"]["/general/v0/general"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]= {"$ref": "#/components/schemas/Elements"}

    # Schema changes
    
    # Add securitySchemes
    # TODO: Implement security per the FastAPI documentation:
    # https://fastapi.tiangolo.com/reference/security/?h=apikey
    openapi_schema["components"]["securitySchemes"] = {
    "ApiKeyAuth":{
        "type":"apiKey",
        "name":"unstructured-api-key",
        "in":"header",
        "x-speakeasy-example": "YOUR_API_KEY"}}
    
    # TODO: Instead of a list of paramaters, creted a PartitionParameters model
    # and declare schema keys (type, format, description) as attributes
    # https://fastapi.tiangolo.com/reference/openapi/models/?h=model
    # Update the schema key from `Body_partition` to `partition_paramaters`
    openapi_schema["components"]["schemas"]["partition_parameters"] = openapi_schema["components"]["schemas"].pop("Body_partition")    
    # Update the schema title for `partition` post endpoint
    openapi_schema["components"]["schemas"]["partition_parameters"]["title"] = "Partition Parameters"
    openapi_schema["components"]["schemas"]["partition_parameters"]["properties"] = {
        "files": {
                        "type": "string",
                        "format": "binary",
                        "description": "The file to extract",
                        "required": "true",
                        "examples": [{
                            "summary": "File to be partitioned",
                            "externalValue": "https://github.com/Unstructured-IO/unstructured/blob/98d3541909f64290b5efb65a226fc3ee8a7cc5ee/example-docs/layout-parser-paper.pdf"
                        }]
                    },
                    "strategy": {
                        "type": "string",
                        "title": "Strategy",
                        "description": "The strategy to use for partitioning PDF/image. Options are fast, hi_res, auto. Default: auto",
                        "examples": ["hi_res"]
                    },
                    "gz_uncompressed_content_type": {
                        "type": "string",
                        "title": "Uncompressed Content Type",
                        "description": "If file is gzipped, use this content type after unzipping",
                        "examples": ["application/pdf"]
                    },
                    "output_format": {
                        "type": "string",
                        "title": "Output Format",
                        "description": "The format of the response. Supported formats are application/json and text/csv. Default: application/json.",
                        "examples": ["application/json"]
                    },
                    "coordinates": {
                        "type": "boolean",
                        "title": "Coordinates",
                        "description": "If true, return coordinates for each element. Default: false"
                    },
                    "encoding": {
                        "type": "string",
                        "title": "Encoding",
                        "description": "The encoding method used to decode the text input. Default: utf-8",
                        "examples": ["utf-8"]
                    },
                    "hi_res_model_name": {
                        "type": "string",
                        "title": "Hi Res Model Name",
                        "description": "The name of the inference model used when strategy is hi_res",
                        "examples": ["yolox"]
                    },
                    "include_page_breaks": {
                        "type": "boolean",
                        "title": "Include Page Breaks",
                        "description": "If True, the output will include page breaks if the filetype supports it. Default: false"
                    },
                    "languages": {
                        "items": {
                            "type": "string",
                            "examples": ["eng"]
                        },
                        "type": "array",
                        "title": "OCR Languages",
                        "default": [],
                        "description": "The languages present in the document, for use in partitioning and/or OCR",
                        "examples": ["[eng]"]
                    },
                    "pdf_infer_table_structure": {
                        "type": "boolean",
                        "title": "Pdf Infer Table Structure",
                        "description": "If True and strategy=hi_res, any Table Elements extracted from a PDF will include an additional metadata field, 'text_as_html', where the value (string) is a just a transformation of the data into an HTML <table>."
                    },
                    "skip_infer_table_types": {
                        "items": {
                            "type": "string",
                            "examples": ["pdf"]
                        },
                        "type": "array",
                        "title": "Skip Infer Table Types",
                        "description": "The document types that you want to skip table extraction with. Default: ['pdf', 'jpg', 'png']"
                    },
                    "xml_keep_tags": {
                        "type": "boolean",
                        "title": "Xml Keep Tags",
                        "description": "If True, will retain the XML tags in the output. Otherwise it will simply extract the text from within the tags. Only applies to partition_xml."
                    },
                    "chunking_strategy": {
                        "type": "string",
                        "title": "Chunking Strategy",
                        "description": "Use one of the supported strategies to chunk the returned elements. Currently supports: by_title",
                        "examples": ["by_title"]
                    },
                    "multipage_sections": {
                        "type": "boolean",
                        "title": "Multipage Sections",
                        "description": "If chunking strategy is set, determines if sections can span multiple sections. Default: true"
                    },
                    "combine_under_n_chars": {
                        "type": "integer",
                        "title": "Combine Under N Chars",
                        "description": "If chunking strategy is set, combine elements until a section reaches a length of n chars. Default: 500",
                        "examples": [500]
                    },
                    "new_after_n_chars": {
                        "type": "integer",
                        "title": "New after n chars",
                        "description": "If chunking strategy is set, cut off new sections after reaching a length of n chars (soft max). Default: 1500",
                        "examples": [1500]
                    },
                    "max_characters": {
                        "type": "integer",
                        "title": "Max Characters",
                        "description": "If chunking strategy is set, cut off new sections after reaching a length of n chars (hard max). Default: 1500",
                        "examples": [1500]
                    }}

    # TODO: Similarly, create an Elements model
    # https://fastapi.tiangolo.com/reference/openapi/models/?h=model
    # Add Elements schema
    openapi_schema["components"]["schemas"]["Elements"] = {
                "type": "array",
                "items":{
                    "Element":{
                        "type":"object",
                        "properties": {
                            "type": {},
                            "element_id": {},
                            "metadata": {},
                            "text": {}}}}}

    app.openapi_schema = openapi_schema
    return app.openapi_schema

app.openapi = custom_openapi

logger.info("Started Unstructured API")
