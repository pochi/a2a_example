# 理解を深める

### success.log参照

- 🙋 Tool #1: get_pricing_service_codesってなんですか？
  - 👨‍🏫 MCP(Pricing mcp server)が提供している機能だよ
  - 🙋 AgentはどうやってMCPの中身を知ってるの？
  - 👨‍🏫 MCPサーバの機能で一覧を取得できる機能があって、それをAgentの引数に渡しているよ
- 🙋 Agentって何を知っているの?
  - 👨‍🏫 今回の実装ではLLMモデルの情報とツール一覧とシステムプロンプトを教えているよ。
- 🙋 success.logにやり取りを何回もしているけど、どんなやり取りをしているの？
  - 👨‍🏫 どうもMCPサーバ側のtoolのdescriptionに従っているよ
  - 🙋 そのdescriptionとかinstructionをagentはどうやって見ているの?
  - 👨‍🏫 丁寧に見ていくとまずはstrands agentのAgentは__caller__を裏側で呼び出していてAgentのイベントループを実装している
  - 👨‍🏫 この中(pythonのthreadとasyncioで非同期にしている)でプロンプトを引き渡しながらinvoke_asyncというメソッドに委譲している
  - 👨‍🏫 invoke_asyncはstream_asyncを呼び出してその結果をAgentResultにcastしているだけ、AgentResultは以下の要素を持ったただのdataclass
    - stop_reason: event_loopを抜け出した理由(end_turn,max_tokensなど)
    - message: modelから帰ってきた最後のメッセージ
    - metrics: イベントループから得られるパフォーマンスメトリクス
    - state: イベントループ内の最終状況
  - 👨‍🏫 stream_asyncはイベントの中を管理するメソッド、このあたりから処理が複雑になっていくので順番に書いておく
    - callback_handlerを設定する、ここはカスタムでも設定できる
    - promptをMessageクラスに押し込める
    - run_loop関数を利用してeventsを取得する(後で詳細を見る)
    - もしeventにcallbackが入っていればその時点でcallback_handlerにそのデータを渡す
    - eventの中に終了条件(event["stop"])が入っていればAgentResultとcallback_handlerに設定する
    - 補足だけど全体をtrace_api.use_spanを利用してモニタリングする仕組みを入れている模様
  - 👨‍🏫 どんなやり取りをしているかはrun_loopまで潜らないと見えてこないのでここも深掘りしていく、与えられたメッセージとパラメータを利用してAgentのloop部分を実装する。
    - hooksで指定されたcallbackがあれば呼び出す(boto3と似たような設計だがBeforeInvocationEventというクラスまで用意されている)
    - {"callback": {"init_event_loop": True, **invocation_state}}をeventとして一度投げる(処理の開始を意味している理解)
    - メッセージを全体管理の中に追加(最後にself.conversation_manager.apply_management(self)しているので履歴管理)
    - self._execute_event_loop_cycle(invocation_state)を利用してeventsを取り出す(後述)
    - eventを見て修正が必要な内容の場合、修正提案のメッセージを採用する。ここはコメントを見るとガードレールなどによる修正を想定しているとのこと
    - このeventをstream_async側に投げる
    - 最後にhooksで指定されたcallbackを呼び出す(AfterInvocationEvent)
  - 👨‍🏫 eventを取得する部分が_execute_event_loop_cycleを見ていく、ここはコンテキスト長のリミットや再送制御なども行っている
    - invocation_state["agent"]に自分自身を設定
    - event_loop_cycleを呼び出す
    - コンテキスト長リミットエラーが発生した場合、コンテキスト長を短くして管理しているAgent全体に同期を取ったのち再度リクエストを送る
  - 👨‍🏫 メインループはevent_loop_cycle(ファイルが専用に切られている)、一つの会話のやり取りを行う(LLMを使った推論、ツール実行、エラーとリカバリ)
    - 最高試行回数を6回、初期の遅延を4秒?、遅延待ちを120秒などTCPの制約的なものを定義している
    - cycle状態とメトリクスを初期化
      - inovattion_state['event_loop_cycle_id']をuuidを使ってセット
      - inovattion_state['request_state']を空のdictで設定
      - yield {"callback": {"start": True}}をAsyncGeneratorとして_execute_event_loop_cycleに返す
      - {"callback": {"start_event_loop": True}}をAsyncGeneratorとして_execute_event_loop_cycleに返す
    - 実行リミットのチェック
    - LLMを使ったメッセージのやり取り
    - ツール実行要求があった時のハンドリング
    - 再帰呼び出し、複数ターン時のツールとのやり取りを管理
    - レポートのためのメトリクス情報を収集
    - エラーハンドリングして必要であればリカバリ







- 🙋 success.logにやり取りを何回もしているけど、何が完了条件なの？

### memo

- 🥲 Amazon Novaだとエラーで動かないので原則Claude使わないといけない