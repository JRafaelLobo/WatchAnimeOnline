FROM nginx:1.27-alpine

COPY Home.html /usr/share/nginx/html/index.html

RUN sed -i 's/listen       80;/listen       3000;/' /etc/nginx/conf.d/default.conf

EXPOSE 3000