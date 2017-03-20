"""Base VM plugin implementations."""
import copy
import time

import requests
import requests.exceptions

from baselaunch import domain_model
from .app_plugin import AppPlugin


class BaseVMAppPlugin(AppPlugin):
    """
    Implementation for the basic VM app.

    It is expected that other apps inherit this class and override or
    complement methods provided here.
    """

    def __init__(self):
        """Init any base app vars."""
        self.base_app = True

    @staticmethod
    def process_app_config(name, cloud_version_config, credentials,
                           app_config):
        """Extract any extra user data from the app config and return it."""
        return app_config.get("config_cloudlaunch", {}).get(
            "instance_user_data", {})

    @staticmethod
    def sanitise_app_config(app_config):
        """Return a sanitized copy of the supplied app config object."""
        return copy.deepcopy(app_config)

    def _get_or_create_kp(self, provider, kp_name):
        """Get or create an SSH key pair with the supplied name."""
        kps = provider.security.key_pairs.find(name=kp_name)
        if kps:
            return kps[0]
        else:
            return provider.security.key_pairs.create(name=kp_name)

    def _get_or_create_sg(self, provider, cloudlaunch_config, sg_name,
                          description):
        """Fetch an existing security group named ``sg_name`` or create one."""
        sgs = provider.security.security_groups.find(name=sg_name)
        for sg1 in sgs:
            for sg2 in sgs:
                if sg1 == sg2:
                    return sg1
        network_id = self._get_network_id(provider, cloudlaunch_config)
        return provider.security.security_groups.create(
            name=sg_name, description=description, network_id=network_id)

    def _get_cb_launch_config(self, provider, image, cloudlaunch_config):
        """Compose a CloudBridge launch config object."""
        lc = None
        if cloudlaunch_config.get("rootStorageType", "instance") == "volume":
            if not lc:
                lc = provider.compute.instances.create_launch_config()
            lc.add_volume_device(source=image,
                                 size=int(cloudlaunch_config.get(
                                          "rootStorageSize", 20)),
                                 is_root=True)
        return lc

    def _get_network_id(self, provider, cloudlaunch_config):
        """
        Figure out the ID of a relevant network.

        Return a ``network`` as supplied in the ``cloudlaunch_config`` or
        the default network on a given provider.
        """
        net_id = cloudlaunch_config.get('network', None)
        if not net_id:
            net = provider.network.get_or_create_default()
            if net:
                net_id = net.id
        return net_id

    def apply_app_firewall_settings(self, provider, cloudlaunch_config):
        """
        Apply firewall settings defined for the app in CloudLaunch settings.

        The following format is expected:

        ```
        "firewall": [
            {
                "rules": [
                    {
                        "from": "22",
                        "to": "22",
                        "cidr": "0.0.0.0/0",
                        "protocol": "tcp"
                    },
                    {
                        "src_group": "MyApp",
                        "from": "1",
                        "to": "65535",
                        "protocol": "tcp"
                    },
                    {
                        "src_group": 'bd9756b8-e9ab-41b1-8a1b-e466a04a997c',
                        "from": "22",
                        "to": "22",
                        "protocol": "tcp"
                    }
                ],
                "securityGroup": "MyApp",
                "description": "My App SG"
            }
        ]
        ```

        Note that if ``src_group`` is supplied, it must be either the current
        security group name or an ID of a different security group for which
        a rule should be added (i.e., different security groups cannot be
        identified by name and their ID must be used).

        :rtype: CloudBridge SecurityGroup
        :return: Security group satisfying the request.
        """
        for group in cloudlaunch_config.get('firewall', []):
            sg_name = group.get('securityGroup') or 'CloudLaunchDefault'
            sg_desc = group.get('description') or 'Created by CloudLaunch'
            sg = self._get_or_create_sg(provider, cloudlaunch_config, sg_name,
                                        sg_desc)
            for rule in group.get('rules', []):
                try:
                    if rule.get('src_group'):
                        sg.add_rule(src_group=sg)
                    else:
                        sg.add_rule(ip_protocol=rule.get('protocol'),
                                    from_port=rule.get('from'),
                                    to_port=rule.get('to'),
                                    cidr_ip=rule.get('cidr'))
                except Exception as e:
                    print(e)
            return sg

    def wait_for_http(self, url, max_retries=200, poll_interval=5):
        """Wait till app is responding at http URL."""
        count = 0
        while count < max_retries:
            time.sleep(poll_interval)
            try:
                r = requests.head(url)
                r.raise_for_status()
                return
            except requests.exceptions.HTTPError as e:
                if e.response.status_code in (401, 403):
                    return
            except requests.exceptions.ConnectionError:
                pass
            count += 1

    def attach_public_ip(self, provider, inst):
        """
        If instance has no public IP, try to attach one.

        The method will attach a random floating IP that's available in the
        account. If there are no available IPs, try to allocate a new one.

        :rtype: ``str``
        :return: The attached IP address. This can be one that's already
                 available on the instance or one that has been attached.
        """
        if not inst.public_ips:
            fip = None
            fips = provider.network.floating_ips()
            for ip in fips:
                if not ip.in_use():
                    fip = ip
            if fip:
                print("Attaching an existing floating IP %s" % fip.public_ip)
                inst.add_floating_ip(fip.public_ip)
            else:
                fip = provider.network.create_floating_ip()
                inst.add_floating_ip(fip.public_ip)
            return fip.public_ip
        elif len(inst.public_ips) > 0:
            return inst.public_ips[0]
        else:
            return None

    def launch_app(self, task, name, cloud_version_config, credentials,
                   app_config, user_data):
        """Initiate the app launch process."""
        cloudlaunch_config = app_config.get("config_cloudlaunch", {})
        provider = domain_model.get_cloud_provider(cloud_version_config.cloud,
                                                   credentials)
        custom_image_id = cloudlaunch_config.get("customImageID", None)
        img = provider.compute.images.get(
            custom_image_id or cloud_version_config.image.image_id)
        task.update_state(state='PROGRESSING',
                          meta={'action': "Retrieving or creating a keypair"})
        kp = self._get_or_create_kp(provider,
                                    cloudlaunch_config.get('keyPair') or
                                    'cloudlaunch_key_pair')
        task.update_state(state='PROGRESSING',
                          meta={'action': "Applying firewall settings"})
        sg = self.apply_app_firewall_settings(provider, cloudlaunch_config)
        cb_launch_config = self._get_cb_launch_config(provider, img,
                                                      cloudlaunch_config)
        inst_type = cloudlaunch_config.get(
            'instanceType', cloud_version_config.default_instance_type)
        placement_zone = cloudlaunch_config.get('placementZone')
        subnet_id = cloudlaunch_config.get('subnet')

        print("Launching with subnet %s and sg %s" % (subnet_id, sg))
        print("Launching with ud:\n%s" % user_data)
        task.update_state(state='PROGRESSING',
                          meta={'action': "Launching an instance of type %s "
                                "with keypair %s in zone %s" %
                                (inst_type, kp.name, placement_zone)})
        inst = provider.compute.instances.create(
            name=name, image=img, instance_type=inst_type, subnet=subnet_id,
            key_pair=kp, security_groups=[sg], zone=placement_zone,
            user_data=user_data, launch_config=cb_launch_config)
        task.update_state(state='PROGRESSING',
                          meta={'action': "Waiting for instance %s" % inst.id})
        inst.wait_till_ready()
        static_ip = cloudlaunch_config.get('staticIP')
        if static_ip:
            task.update_state(state='PROGRESSING',
                              meta={'action': "Assigning requested floating "
                                    "IP: %s" % static_ip})
            inst.add_floating_ip(static_ip)
            inst.refresh()
        results = {}
        results['keyPair'] = {'id': kp.id, 'name': kp.name,
                              'material': kp.material}
        results['securityGroup'] = {'id': sg.id, 'name': sg.name}
        results['instance'] = {'id': inst.id}
        results['publicIP'] = self.attach_public_ip(provider, inst)
        task.update_state(
            state='PROGRESSING',
            meta={'action': "Instance creation successful. Public IP "
                  "(if available): %s" % results['publicIP']})
        if self.base_app:
            if results['publicIP']:
                results['applicationURL'] = 'http://%s/' % results['publicIP']
                task.update_state(
                    state='PROGRESSING',
                    meta={'action': "Waiting for application to become ready "
                          "at %s" % results['applicationURL']})
                self.wait_for_http(results['applicationURL'])
            else:
                results['applicationURL'] = 'N/A'
        return {'cloudLaunch': results}
