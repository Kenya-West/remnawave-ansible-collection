=================================
kenyawest.remnawave Release Notes
=================================

.. contents:: Topics

v1.2.0
======

Minor Changes
-------------

- config_profile - add ``tags``, authoritative when set, applied through the panel's dedicated tags endpoint.
- external_squad - add ``tags``, authoritative when set, so existing squads can be retagged as well as created tagged.
- internal_squad - add ``tags``, authoritative when set, applied through the panel's dedicated tags endpoint.
- node, host - validate ``tags`` against the panel's format (at most 10 tags of up to 36 uppercase letters, digits, underscores and colons) before sending anything, failing with a message that names the offending tag.
- remnawave role - add ``remnawave_gather`` to read entities back after the desired state is applied, published as the ``remnawave_gathered`` fact.
- remnawave role - pass ``tags`` through for ``remnawave_config_profiles``, ``remnawave_internal_squads`` and ``remnawave_external_squads``.
- system_info - add ``timezone``, sent as the bandwidth statistics' ``tz`` query parameter.
- user_info - add lookups by ``id`` and ``short_uuid``.
- user_info - add the stream endpoint's filters ``status``, ``traffic_limit_strategy``, ``telegram_id``, ``email``, ``tag`` and ``external_squad`` (by name or UUID), with ``cursor`` pagination returning ``next_cursor`` and ``has_more``.
- user_info - add the table endpoint's ``filters``, ``filter_modes``, ``global_filter_mode`` and ``sorting``, with ``start``/``size`` pagination returning ``total``.

v1.1.0
======

Minor Changes
-------------

- host - add ``exclude_from_subscription_types``, authoritative when set, to leave a host out of some subscription formats.
- host - add ``internal_squads`` (``mode`` of ``exclude``/``allow_only`` plus a squad list by name or UUID) to govern which internal squads see a host.
- host - add ``override_sni_from_address`` and ``keep_sni_blank``, the SNI overrides a chain entry needs when the address it publishes is not the domain the exit node terminates TLS for.
- host - add ``vless_route_id``, the route id a config profile's routing rules match on to send a host's traffic through a particular outbound or balancer. It takes an integer between 0 and 65535, and an empty string clears it.

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
