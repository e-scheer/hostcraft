import js from '@eslint/js'
import vue from 'eslint-plugin-vue'
import vueTs from '@vue/eslint-config-typescript'
import stylistic from '@stylistic/eslint-plugin'

export default [
  { ignores: ['dist/**', 'node_modules/**'] },
  js.configs.recommended,
  ...vue.configs['flat/recommended'],
  ...vueTs(),
  {
    plugins: { '@stylistic': stylistic },
    rules: {
      'vue/multi-word-component-names': 'off',
      'vue/no-unused-vars': 'warn',
      '@typescript-eslint/no-unused-vars': ['warn', { argsIgnorePattern: '^_' }],
    },
  },
]
