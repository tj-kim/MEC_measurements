Install Nginx server
  sudo apt-get update
  sudo apt-get install nginx
  sudo apt-get install apache2-utils

Create a password file:
```
  sudo htpasswd -c /etc/nginx/.htpasswd vanmao_ngo
```

If you want to add more user:
```
  sudo htpasswd /etc/nginx/.htpasswd wnds
```
First, make a Prometheus-specific copy of the default Nginx configuration file so that you can revert back to the defaults later if you run into a problem.
```
sudo cp /etc/nginx/sites-available/default /etc/nginx/sites-available/prometheus
```
Then, open the new configuration file.
```
sudo nano /etc/nginx/sites-available/prometheus
```
Change /etc/nginx/site-availabel/prometheus
```
...
    location / {
        auth_basic "Prometheus server authentication";
        auth_basic_user_file /etc/nginx/.htpasswd;
        proxy_pass http://localhost:9090;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
...
```
```
sudo rm /etc/nginx/sites-enabled/default
sudo ln -s /etc/nginx/sites-available/prometheus /etc/nginx/sites-enabled/
```
Before restarting Nginx, check the configuration for errors using the following command:
```
sudo nginx -t
```
The output should indicate that the syntax is ok and the test is successful. If you receive an error message, follow the on-screen instructions to fix the problem before proceeding to the next step.

Output of Nginx configuration tests
```
nginx: the configuration file /etc/nginx/nginx.conf syntax is ok
nginx: configuration file /etc/nginx/nginx.conf test is successful
```
Then, reload Nginx to incorporate all of the changes.
```
sudo systemctl reload nginx
```
Verify that Nginx is up and running.
```
sudo systemctl status nginx
```

