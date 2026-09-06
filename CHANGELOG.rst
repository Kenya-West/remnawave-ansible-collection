=================================
kenyawest.remnawave Release Notes
=================================

.. contents:: Topics

v1.0.2
======

Minor Changes
-------------

- remnawave role - add ``remnawave_snippets``, applied before ``remnawave_config_profiles`` because profiles embed snippets.
- snippet - manage Remnawave snippets declaratively, addressed by name, with the supplied content treated as authoritative.
- snippet - run the panel's sync action against the config profiles embedding a snippet whenever the snippet changed, controlled by the new ``sync`` option (``on_change`` by default, or ``never``/``always``).
- snippet_info - retrieve one snippet by name or list all of them.

v0.1.1
======

Minor Changes
-------------

- docs - add contributing instructions
- docs - add version bump instructions
- python - migrate from pip to uv everywhere
- tests - add tests

v0.1.0
======

Release Summary
---------------

Initial release. Developed and tested against the Remnawave API specification v3.4.3, including a live panel run.

Minor Changes
-------------

- Every module supports check mode and diff mode, including the cascade.
- ``host_info`` filters by ``remark`` or ``address`` and returns every match, which is how to act on all the hosts serving one domain.
- ``host`` accepts a ``nodes`` option to declare that binding, by node name.
- ``host`` addresses panels by ``remark`` or, with ``identify_by: address``, by domain, so a list of domains needs no invented remarks; a host created that way takes its address as its remark, and ``remark`` becomes an ordinary field that can rename it. An identifier matching several hosts fails the task instead of picking one.
- ``node`` can carry the hosts bound to it along when a node is taken out of service, through ``linked_hosts`` (``ignore``/``enable``/``disable``/``delete``). Hosts bound to no node are never affected.
- ``user``, ``node`` and ``host`` share one ``state`` property: ``present`` (exists, enabled/disabled left alone), ``enabled``, ``disabled`` and ``absent``.

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
