import base64
import dataclasses
import zlib
from typing import Optional

import json
from contextlib import asynccontextmanager

import uvicorn
from aiohttp import ClientSession
from fastapi import FastAPI, Cookie, Response, Depends, Body
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import RedirectResponse

from hastygram import api

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    # TODO
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@dataclasses.dataclass(frozen=True)
class URLProfile:
    username: str
    fullname: str
    thumb: str
    biography: str
    website: str
    follower_count: int

    @classmethod
    def depends(cls, p: Optional[str] = None):
        try:
            return cls.decode(p)
        except:
            return None

    @classmethod
    def decode(cls, encoded: str) -> "URLProfile":
        data = json.loads(zlib.decompress(base64.urlsafe_b64decode(encoded.encode("ascii"))))
        return cls(*data)

    def encode(self) -> str:
        data = json.dumps(dataclasses.astuple(self))
        data = zlib.compress(data.encode("ascii"), level=9)
        return base64.urlsafe_b64encode(data).decode("ascii")


@asynccontextmanager
async def http(headers=None, cookies=None):
    async with ClientSession(headers=headers, cookies=cookies) as sess:
        yield sess


async def session(sessionid: Optional[str] = Cookie(None)):
    async with http(headers=api.headers(),
                    cookies=None if sessionid is None else {"sessionid": sessionid}) as h:
        yield h


session_cm = asynccontextmanager(session)


@app.post("/authenticate")
async def authenticate(response: Response, sessionid: str = Body(..., embed=True)):
    async with session_cm(sessionid) as s:
        info = await api.self_info(s)
    id = info["id"]
    username = info["username"]
    response.set_cookie("sessionid", sessionid, httponly=False, expires=3600 * 24 * 7)
    return {
        "id": id,
        "name": username,
    }


@app.get("/{username}")
async def user_redirect(username: str, limit: Optional[int] = 12, s=Depends(session)):
    async with s:
        user = await api.user_data(s, username)
    user_id = user["id"]
    profile = URLProfile(username=user["username"],
                         fullname=user["full_name"],
                         thumb=user["profile_pic_url_hd"],
                         biography=user["biography"][:240],
                         website=user["external_url"],
                         follower_count=user["edge_followed_by"]["count"])
    return RedirectResponse(f"/u/{user_id}?limit={limit}&p={profile.encode()}")


@app.get("/u/{uid}")
async def user_profile(uid: str, after: Optional[str] = None, limit: Optional[int] = 12,
                       profile=Depends(URLProfile.depends), s=Depends(session)):
    async with s:
        feed = await api.user_feed(s, uid, limit=limit, after=after)

    return {"feed": feed, "profile": profile}


if __name__ == '__main__':
    uvicorn.run(app, port=8000)