
# ใช้ฟีเจอร์ RUN --mount=type=secret ต้องใส่ syntax directive นี้
# (ต้องเปิดใช้ BuildKit ตอน build)
# syntax=docker/dockerfile:1.7-labs

FROM python:3.11-alpine

# ติดตั้งแพ็กเกจระบบด้วย apk (ไม่ใช่ apt)
# - ca-certificates, tzdata: สำหรับ SSL/เวลา
# - git: ให้ pip ดึงแพ็กเกจจาก VCS ได้
# - build-base: (ออปชัน) เผื่อมีแพ็กเกจที่ต้องคอมไพล์ wheel
RUN apk add --no-cache ca-certificates tzdata git build-base \
    && update-ca-certificates

# สร้าง user/โฟลเดอร์ทำงาน
ENV FLOWER_DATA_DIR=/data \
    PYTHONUNBUFFERED=1 \
    PYTHONHASHSEED=random \
    PYTHONDONTWRITEBYTECODE=1
WORKDIR $FLOWER_DATA_DIR

# ติดตั้ง dependencies ผ่าน pip
# - ใช้ BuildKit secret ชื่อ git_token (ส่งค่าเข้ามาจาก env GIT_TOKEN ตอน build)
# - แนะนำติดตั้ง celery ด้วย เพราะคุณใช้ `CMD ["celery", "flower"]`
# - ถ้า token มีอักขระพิเศษ อาจต้อง URL-encode
ARG FLOWER_REF=feature/filter-box
RUN --mount=type=secret,id=git_token \
    TOKEN="$(cat /run/secrets/git_token)" && \
    pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
      celery \
      redis \
      "git+https://oauth2:${TOKEN}@git.iapp.co.th/chonlasit/flower-v2.0.0.git@${FLOWER_REF}"

# เตรียม user ปลอดภัย
RUN addgroup -g 1000 flower && \
    adduser -u 1000 -G flower -D flower && \
    chown -R flower:flower "$FLOWER_DATA_DIR"
USER flower

VOLUME $FLOWER_DATA_DIR
EXPOSE 5555

# หมายเหตุ: คุณใช้ celery CLI เรียก flower จึงต้องมี celery ติดตั้งไว้แล้ว
# ถ้าอยากเรียกตรง ๆ ก็ใช้ `["flower"]` ได้เช่นกัน (ขึ้นกับแพ็กเกจที่คุณ fork)
CMD ["celery", "flower"]

# izsLrg-TBz_gTH_C9pnc