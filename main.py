import aiofiles
from sse_starlette.sse import EventSourceResponse
import asyncio
from threading import Thread
from fastapi import FastAPI, UploadFile, Request
from fastapi.staticfiles import StaticFiles
import shortuuid
import os

app = FastAPI()

if not os.path.exists('data'):
    os.mkdir('data')

app.mount("/data", StaticFiles(directory="data"), name="data")

STATE = dict()
STREAM_DELAY = 0.5  # second
RETRY_TIMEOUT = 15000  # milisecond


@app.get('/task/{task_id}/stream')
async def message_stream(task_id: str, request: Request):
    async def event_generator():
        global STATE
        while True:
            if await request.is_disconnected():
                break
            if task_id not in STATE:
                yield {
                    "event": "error",
                    "id": "message_id",
                    "retry": RETRY_TIMEOUT,
                    "data": 'Task not found'
                }
            else:
                task = STATE[task_id]
                if task['status'] == 'done':
                    yield {
                        "event": "result",
                        "id": "message_id",
                        "retry": RETRY_TIMEOUT,
                        "data": task['result']
                    }
                    if await request.is_disconnected():
                        del STATE[task_id]
                        break
                else:
                    yield {
                        "event": "progress",
                        "id": "message_id",
                        "retry": RETRY_TIMEOUT,
                        "data": task['progress']
                    }

            await asyncio.sleep(STREAM_DELAY)

    return EventSourceResponse(event_generator())


async def helper(task_id: str):
    global STATE
    STATE[task_id] = dict()
    STATE[task_id]['status'] = 'pending'
    STATE[task_id]['progress'] = 0
    STATE[task_id]['result'] = {}

    with open('annotations.json', 'r') as j:
        STATE[task_id]['result'] = j.read()

    for i in range(101):
        STATE[task_id]['progress'] = i
        await asyncio.sleep(0.05)
    STATE[task_id]['status'] = 'done'

    # STATE[task_id]['results'] = {}


@app.post("/upload")
async def create_upload_files(files: list[UploadFile]):
    task_id = shortuuid.uuid()
    task_dir = f'data/{task_id}/'
    os.mkdir(task_dir)
    for index, file in enumerate(files):
        filename = task_dir + str(index) + '.' + file.filename.split(".")[-1]
        async with aiofiles.open(filename, 'wb') as out_file:
            content = await file.read()
            await out_file.write(content)
    Thread(target=asyncio.run, args=(helper(task_id),)).start()
    return {"task_id": task_id}
