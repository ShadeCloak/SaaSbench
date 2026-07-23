import json
from features.models import Feature, FeatureState, FeatureSegment, FeatureStateValue
from segments.models import Segment, SegmentRule, Condition
from environments.models import Environment
from environments.identities.models import Identity
from environments.identities.traits.models import Trait
from projects.models import Project

env = (Environment.objects.filter(name="EvalSetupEnv").order_by("id").first()
       or Environment.objects.order_by("id").first())
project = env.project

if project.hide_disabled_flags:
    project.hide_disabled_flags = False
    project.save()
if env.hide_sensitive_data:
    env.hide_sensitive_data = False
    env.save()


def set_value(fs, value):
    try:
        fsv = fs.feature_state_value
    except FeatureStateValue.DoesNotExist:
        fsv = FeatureStateValue.objects.create(feature_state=fs)
    fsv.type = "unicode"
    fsv.string_value = value
    fsv.integer_value = None
    fsv.boolean_value = None
    fsv.save()


def get_or_create_feature(name, default_enabled=False, initial_value="default_val"):
    f, created = Feature.objects.get_or_create(
        name=name, project=project,
        defaults={"default_enabled": default_enabled, "initial_value": initial_value},
    )
    return f


# ---------------- SEGMENT chain fixture ----------------
seg_feat = get_or_create_feature("eval_seg_target", default_enabled=False, initial_value="off")
seg_segment, _ = Segment.objects.get_or_create(name="eval_seg_segment", project=project)
seg_segment.rules.all().delete()
root = SegmentRule.objects.create(segment=seg_segment, type=SegmentRule.ALL_RULE)
Condition.objects.create(rule=root, operator="EQUAL", property="country", value="US")
child = SegmentRule.objects.create(rule=root, type=SegmentRule.ANY_RULE)
Condition.objects.create(rule=child, operator="EQUAL", property="plan", value="premium")
Condition.objects.create(rule=child, operator="EQUAL", property="plan", value="enterprise")
seg_fs, _ = FeatureSegment.objects.get_or_create(
    feature=seg_feat, segment=seg_segment, environment=env,
    defaults={"priority": 0},
)
ov = FeatureState.objects.filter(feature=seg_feat, feature_segment=seg_fs, environment=env).first()
if not ov:
    ov = FeatureState.objects.create(feature=seg_feat, feature_segment=seg_fs, environment=env, enabled=True)
else:
    ov.enabled = True; ov.save()
print("SEG feature id", seg_feat.id, "segment id", seg_segment.id, "fs override id", ov.id)

# ---------------- PRIORITY chain fixture ----------------
prio_feat = get_or_create_feature("eval_prio_target", default_enabled=False, initial_value="default_val")
env_default = FeatureState.objects.filter(feature=prio_feat, environment=env, feature_segment__isnull=True, identity__isnull=True).first()
if env_default:
    set_value(env_default, "default_val")
prio_segment, _ = Segment.objects.get_or_create(name="eval_prio_segment", project=project)
prio_segment.rules.all().delete()
proot = SegmentRule.objects.create(segment=prio_segment, type=SegmentRule.ALL_RULE)
Condition.objects.create(rule=proot, operator="EQUAL", property="tier", value="silver")
prio_fs, _ = FeatureSegment.objects.get_or_create(
    feature=prio_feat, segment=prio_segment, environment=env, defaults={"priority": 0})
seg_ov = FeatureState.objects.filter(feature=prio_feat, feature_segment=prio_fs, environment=env).first()
if not seg_ov:
    seg_ov = FeatureState.objects.create(feature=prio_feat, feature_segment=prio_fs, environment=env, enabled=True)
set_value(seg_ov, "segment_val")

id_override, _ = Identity.objects.get_or_create(identifier="eval-override-1", environment=env)
id_segment, _ = Identity.objects.get_or_create(identifier="eval-segment-1", environment=env)
id_default, _ = Identity.objects.get_or_create(identifier="eval-default-only", environment=env)
for ident in (id_segment, id_override):
    Trait.objects.update_or_create(
        identity=ident, trait_key="tier",
        defaults={"value_type": "unicode", "string_value": "silver"})
id_ov = FeatureState.objects.filter(feature=prio_feat, identity=id_override, environment=env).first()
if not id_ov:
    id_ov = FeatureState.objects.create(feature=prio_feat, identity=id_override, environment=env, enabled=True)
set_value(id_ov, "identity_val")
print("PRIO feature id", prio_feat.id, "segment id", prio_segment.id)
print("identities:", id_override.id, id_segment.id, id_default.id)
print("SEED DONE")
