##
#Example Puppet file for zfs-offlne-backup
##

class zfs::autobackup {    

    package { 'mbuffer':
      ensure => '20160613-1.el7',
    }

}

class zfs::autobackup::master {

    $cron = $::hostname ? {
      /.*-t\d\d$/    => '/opt/admin/scripts/offline-replication/run_backup.py 00:50:56:a2:cf:9e zfs-backup-t01 200M 9090 databackup -v2',
      /.*-i\d\d$/    => '/opt/admin/scripts/offline-replication/run_backup.py 00:50:56:a2:d9:40 zfs-backup-i01 200M 9090 databackup -v2',
      /.*-p\d\d$/    => '/opt/admin/scripts/offline-replication/run_backup.py 00:84:ed:74:5f:f2 zfs-backup-p01 2G 9090 databackup -p -v2',
    }
	# The admin foleder gets mounted in my base config

    file { '/root/.ssh':
      ensure   => 'directory',
      group    => '0',
      mode     => '755',
      owner    => '0',
      selrange => 's0',
      selrole  => 'object_r',
      seltype  => 'ssh_home_t',
      seluser  => 'unconfined_u',
    }

    file { '/root/.ssh/id_rsa':
      ensure   => 'file',
      group    => '0',
      mode     => '600',
      owner    => '0',
      selrange => 's0',
      selrole  => 'object_r',
      seltype  => 'ssh_home_t',
      seluser  => 'unconfined_u',
      source   => 'puppet:///modules/zfs/id_rsa',
      require  => File['/root/.ssh'],
    }

    file { '/root/.ssh/id_rsa.pub':
      ensure   => 'file',
      group    => '0',
      mode     => '644',
      owner    => '0',
      selrange => 's0',
      selrole  => 'object_r',
      seltype  => 'ssh_home_t',
      seluser  => 'unconfined_u',
      source   => 'puppet:///modules/zfs/id_rsa.pub',
      require  => File['/root/.ssh'],
    }


    cron { 'backup server':
      ensure  => 'present',
      command => $cron,
      hour    => ['5'],
      minute  => ['30'],
      target  => 'root',
      user    => 'root',
      weekday => ['5'],
    }

}

class zfs::autobackup::backup {
    include iptables::mbuffer #Firewall rule to allow port used by mbuffer

    group { 'backup':
      ensure => 'present',
      gid    => '10002',
    }

    user { 'backup':
      ensure           => 'present',
      gid              => '10002',
      home             => '/home/backup',
      password         => '!!',
      password_max_age => '99999',
      password_min_age => '0',
      shell            => '/bin/bash',
      uid              => '10002',
      purge_ssh_keys   => true,
      managehome       => true,
    }

    file { '/home/backup/.ssh':
      ensure   => 'directory',
      group    => '10002',
      mode     => '755',
      owner    => '10002',
      selrange => 's0',
      selrole  => 'object_r',
      seltype  => 'ssh_home_t',
      seluser  => 'unconfined_u',
      require  => User['backup'],
    }

    file { '/etc/sudoers.d/10-sudoers-backup':
      ensure   => 'file',
      group    => '0',
      mode     => '440',
      owner    => '0',
      selrange => 's0',
      selrole  => 'object_r',
      seltype  => 'etc_t',
      seluser  => 'system_u',
      source   => 'puppet:///modules/zfs/10-sudoers-backup',
    }

    ssh_authorized_key { 'backup':
      ensure => present,
      user   => 'backup',
      type   => 'ssh-rsa',
      key    => '*key*',
      require => File['/home/backup/.ssh'],
    }    

}
