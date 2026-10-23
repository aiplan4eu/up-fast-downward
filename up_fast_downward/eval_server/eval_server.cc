// Copied into src/search/search_algorithms by up_fast_downward/_custom_build.py.

#include "../axioms.h"
#include "../evaluation_context.h"
#include "../evaluator.h"
#include "../search_algorithm.h"

#include "../plugins/plugin.h"
#include "../utils/system.h"

#include <iostream>
#include <set>
#include <sstream>

using namespace std;

namespace eval_server {
/*
  Reads states from stdin, one per line as the space-separated values of all
  variables, and prints "@<h>" or "@inf" for each of them. Prints "@ready" once
  the evaluator is constructed. Lines without the "@" prefix are log output.
*/
class EvalServer : public SearchAlgorithm {
    shared_ptr<Evaluator> evaluator;
protected:
    virtual SearchStatus step() override;
public:
    EvalServer(
        const shared_ptr<AbstractTask> &task,
        const shared_ptr<Evaluator> &evaluator, OperatorCost cost_type,
        int bound, double max_time, const string &description,
        utils::Verbosity verbosity)
        : SearchAlgorithm(
              task, cost_type, bound, max_time, description, verbosity),
          evaluator(evaluator) {
    }

    virtual void print_statistics() const override {
    }
    virtual bool is_complete_within_bound() const override {
        return false;
    }
};

SearchStatus EvalServer::step() {
    set<Evaluator *> path_dependent_evaluators;
    evaluator->get_path_dependent_evaluators(path_dependent_evaluators);
    if (!path_dependent_evaluators.empty()) {
        cerr << "eval_server does not support path-dependent evaluators."
             << endl;
        utils::exit_with(utils::ExitCode::SEARCH_UNSUPPORTED);
    }
    AxiomEvaluator &axiom_evaluator = g_axiom_evaluators[task_proxy];
    int num_variables = task_proxy.get_variables().size();
    cout << "@ready" << endl;

    string line;
    while (getline(cin, line)) {
        vector<int> values(num_variables);
        istringstream in(line);
        for (int &value : values) {
            in >> value;
        }
        axiom_evaluator.evaluate(values);
        /*
          Heuristics cache values per registered state, so each query gets a
          fresh registry; its only state carries the queried values unpacked.
        */
        StateRegistry registry(task_proxy);
        State state = registry.lookup_state(
            registry.get_initial_state().get_id(), move(values));
        EvaluationContext eval_context(state);
        int h = eval_context.get_evaluator_value_or_infinity(evaluator.get());
        cout << "@" << (h == EvaluationResult::INFTY ? "inf" : to_string(h))
             << endl;
    }
    return FAILED;
}

class EvalServerFeature
    : public plugins::TypedFeature<TaskIndependentSearchAlgorithm> {
public:
    EvalServerFeature() : TypedFeature("eval_server") {
        document_title("Evaluator server");
        document_synopsis(
            "Prints the value of an evaluator for states read from stdin.");
        add_option<shared_ptr<TaskIndependentEvaluator>>("eval", "evaluator");
        add_search_algorithm_options_to_feature(*this, "eval_server");
    }

    virtual shared_ptr<TaskIndependentSearchAlgorithm> create_component(
        const plugins::Options &opts) const override {
        return components::make_auto_task_independent_component<
            EvalServer, SearchAlgorithm>(
            opts.get<shared_ptr<TaskIndependentEvaluator>>("eval"),
            get_search_algorithm_arguments_from_options(opts));
    }
};

static plugins::FeaturePlugin<EvalServerFeature> _plugin;
}
