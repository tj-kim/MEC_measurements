# Requirements
- Virtual box
- Vagrant

# Virtual machines with vagrant
## VMs control
### Provision
In the first time, we need start provision to automatically install all necessary dependencies.
```
vagrant up --provision
```

After that, we only need call `vagrant up` to start VMs. When we update our
provision script, we want VMs update their configurations too. In this case, we call the following command to update provision.
```
vagrant reload --provision
```

### Use VMs
Start:
```
vagrant up
```

Stop:
```
vagrant halt
```

Remove:
```
vagrant destroy
```

Login:
```
vagrant ssh <docker1|docker2|docker3>
```

