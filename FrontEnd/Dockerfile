FROM nginx:1.27-alpine

COPY index.html /usr/share/nginx/html/index.html
COPY assets /usr/share/nginx/html/assets

RUN sed -i 's/listen       80;/listen       3000;/' /etc/nginx/conf.d/default.conf

EXPOSE 3000