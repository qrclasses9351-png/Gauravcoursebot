FROM python:3.10.8-slim-bullseye
RUN apt-get update -y && apt-get upgrade -y \
    && apt-get install -y --no-install-recommends gcc libffi-dev musl-dev ffmpeg aria2 python3-pip \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*
RUN useradd -ms /bin/bash ytuser
USER ytuser
WORKDIR /home/ytuser/app
RUN pip install --upgrade pip yt-dlp requests tqdm
COPY --chown=ytuser:ytuser . .
RUN pip3 install --no-cache-dir --upgrade --requirement requirements.txt || true
RUN pip install -U yt-dlp
CMD ["python3", "download_videos_pdfs.py"]
 




