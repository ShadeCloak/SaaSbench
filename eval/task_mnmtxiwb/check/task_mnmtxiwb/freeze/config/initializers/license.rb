# frozen_string_literal: true

require "lago_utils"

License = LagoUtils::License.new(Rails.application.config.license_url)

# [SaaSBench eval patch] 评测需要 premium feature（createApiKey / multiple
# api keys / premium integrations 等）。原版 License 在 ENV["LAGO_LICENSE"] 为空
# 时 @premium 永远 false → puma 进程里 createApiKey 返回 feature_unavailable →
# 测脚本里的 `rails runner` 临时设 @premium=true 只在 runner 进程内生效，puma
# 看不到。这里直接在 initializer 里强制设上，puma/sidekiq 启动加载时就持久。
License.instance_variable_set(:@premium, true)

License.verify unless Rails.env.test?
