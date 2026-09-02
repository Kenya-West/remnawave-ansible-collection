=================================
kenyawest.remnawave Release Notes
=================================

.. contents:: Topics

v0.1.0
======

Release Summary
---------------

Initial release. Developed and tested against the Remnawave API
specification v3.4.3, including a live panel run.

Highlights
----------

- ``user``, ``node`` and ``host`` share one ``state`` property:
  ``present`` (exists, enabled/disabled left alone), ``enabled``,
  ``disabled`` and ``absent``.
- ``node`` can carry the hosts bound to it along when a node is taken out
  of service, through ``linked_hosts``
  (``ignore``/``enable``/``disable``/``delete``). Hosts bound to no node are
  never affected.
- ``host`` accepts a ``nodes`` option to declare that binding, by node name.
- Every module supports check mode and diff mode, including the cascade.

New Modules
-----------

- kenyawest.remnawave.api - Call an arbitrary Remnawave API endpoint
- kenyawest.remnawave.config_profile - Manage Remnawave config profiles
- kenyawest.remnawave.config_profile_info - Retrieve Remnawave config profiles
- kenyawest.remnawave.external_squad - Manage Remnawave external squads
- kenyawest.remnawave.external_squad_info - Retrieve Remnawave external squads
- kenyawest.remnawave.host - Manage Remnawave subscription hosts
- kenyawest.remnawave.host_info - Retrieve Remnawave hosts
- kenyawest.remnawave.internal_squad - Manage Remnawave internal squads
- kenyawest.remnawave.internal_squad_info - Retrieve Remnawave internal squads
- kenyawest.remnawave.node - Manage Remnawave nodes
- kenyawest.remnawave.node_info - Retrieve Remnawave nodes
- kenyawest.remnawave.subscription_settings - Manage Remnawave subscription settings
- kenyawest.remnawave.system_info - Retrieve Remnawave system information
- kenyawest.remnawave.user - Manage Remnawave panel users
- kenyawest.remnawave.user_info - Retrieve Remnawave users

New Roles
---------

- kenyawest.remnawave.remnawave - Apply a complete desired state to a panel
