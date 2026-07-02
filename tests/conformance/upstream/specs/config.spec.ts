/**
 * Copyright (c) Microsoft Corporation.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 */

import { test, expect, parseResponse } from '../fixtures/fixtures.js';

test.use({ mcpCaps: ['config'] });

test('browser_get_config returns resolved server config', async ({ client }) => {
  const result = await client.callTool({
    name: 'browser_get_config',
  });

  expect(result.isError).toBeFalsy();
  const parsed = parseResponse(result);
  const config = JSON.parse(parsed.result);

  expect(config.browser).toBeTruthy();
  expect(config.capabilities ?? config.caps).toContain('config');
  expect(config.codegen).toBe('python');
});
